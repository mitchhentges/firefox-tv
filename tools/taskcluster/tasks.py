import datetime
import json
import os

import taskcluster


def script_to_bash_command(script):
    single_command = ' && '.join([line.strip() for line in script.split('\n') if line.strip()])
    return [
        '/bin/bash',
        '--login',
        '-cx',
        f'export TERM=dumb && {single_command}'
    ]


class TaskBuilder:
    def __init__(self, owner, repo_url, commit, task_group_id):
        self.owner = owner
        self.repo_url = repo_url
        self.commit = commit
        self.task_group_id = task_group_id

    def craft_pr_task(self, branch):
        script = f'''
        git fetch {self.repo_url} {branch}
        git config advice.detachedHead false
        git checkout {self.commit}
        yes | sdkmanager --licenses
        ./gradlew -PisPullRequest clean assembleSystem assembleAndroidTest lint checkstyle ktlint pmd detekt test
        ./gradlew -Pcoverage jacocoSystemDebugTestReport
        ./tools/taskcluster/upload-coverage-report.sh
        ./tools/taskcluster/download-firebase-sdk.sh
        ./tools/taskcluster/google-firebase-testlab-login.sh
        ./tools/taskcluster/execute-firebase-test.sh system/debug app-system-debug model=sailfish,version=25,orientation=landscape
        '''

        return self._craft_shell_task(
            "Firefox for Amazon's Fire TV - Build - Pull Request",
            script,
            ['secrets:get:project/mobile/firefox-tv/tokens'],
            {
                'public/reports': {
                    'type': 'directory',
                    'path': '/opt/firefox-tv/app/builds/reports',
                    'expires': taskcluster.stringDate(taskcluster.fromNow('1 week')),
                }
            }
        )

    def craft_landed_task(self):
        script = f'''
        git fetch {self.repo_url}
        git config advice.detachedHead false
        git checkout {self.commit}
        yes | sdkmanager --licenses
        ./gradlew -PisPullRequest clean assembleSystem assembleAndroidTest lint checkstyle ktlint pmd detekt test
        python ./tools/taskcluster/get-bitbar-token.py
        python ./tools/taskcluster/execute-bitbar-test.py system/debug app-system-debug
        '''

        return self._craft_shell_task(
            "Firefox for Amazon's Fire TV - Build - Master",
            script,
            ['secrets:get:project/mobile/firefox-tv/tokens'],
            {
                'public': {
                    'type': 'directory',
                    'path': '/opt/firefox-tv/app/builds/reports',
                    'expires': taskcluster.stringDate(taskcluster.fromNow('1 week')),
                }
            }
        )

    def craft_release_build_task(self, tag):
        script = f'''
        git fetch {self.repo_url} --tags
        git config advice.detachedHead false
        git checkout {tag}
        yes | sdkmanager --licenses
        python tools/taskcluster/get-sentry-token.py
        python tools/taskcluster/get-pocket-token.py
        ./gradlew --no-daemon clean test assembleSystemRelease
        '''

        return self._craft_shell_task(
            f'Firefox for Fire TV - Release build {tag}',
            script,
            ['secrets:get:project/mobile/firefox-tv/tokens'],
            {
                'public/build/target.apk': {
                    'type': 'file',
                    'path': '/opt/firefox-tv/app/build/outputs/apk/system/release/app-system-release-unsigned.apk',
                    'expires': taskcluster.stringDate(taskcluster.fromNow('1 week')),
                },
            },
            chain_of_trust=True, # Needed for sign and push task verification
        )

    def _craft_shell_task(self, name, script, scopes, artifacts, *, chain_of_trust=False):
        single_command = ' && '.join([line.strip() for line in script.split('\n') if line.strip()])
        bash_command = [
            '/bin/bash',
            '--login',
            '-cx',
            f'export TERM=dumb && {single_command}'
        ]

        return self._craft_base_task(name, {
            'provisionerId': 'aws-provisioner-v1',
            'workerType': 'github-worker',
            'scopes': scopes,
            'payload': {
                'maxRunTime': 3600,
                'deadline': taskcluster.stringDate(taskcluster.fromNow('2 hours')),
                'image': 'mozillamobile/firefox-tv:2.3',
                'command': bash_command,
                'artifacts': artifacts,
                'features': {
                    'taskclusterProxy': True,
                    'chainOfTrust': chain_of_trust,
                }
            }
        })

    def craft_sign_for_github_task(self, build_task_id, is_staging):
        return self._craft_base_task('Sign for Github', {
            'provisionerId': 'scriptworker-prov-v1',
            'workerType': 'mobile-signing-dep-v1' if is_staging else 'mobile-signing-v1',
            'scopes': [
                'project:mobile:firefox-tv:releng:signing:format:autograph_apk',
                'project:mobile:firefox-tv:releng:signing:cert:{}-signing'.format(
                    'dep' if is_staging else 'production')
            ],
            'dependencies': [build_task_id],
            'payload': {
                'upstreamArtifacts': [{
                    'paths': ['public/build/target.apk'],
                    'formats': ['autograph_apk'],
                    'taskId': build_task_id,
                    'taskType': 'build',
                }]
            },
        })

    def craft_amazon_task(self, build_task_id, is_staging):
        return self._craft_base_task('Push to Amazon', {
            'provisionerId': 'scriptworker-prov-v1',
            'workerType': 'mobile-pushapk-dep-v1' if is_staging else 'mobile-pushapk-v1',
            'scopes': [
                'project:mobile:firefox-tv:releng:googleplay:product:firefox-tv{}'.format(
                    ':dep' if is_staging else ''
                )
            ],
            'dependencies': [build_task_id],
            'payload': {
                'target_store': 'amazon',
                'channel': 'production',
                'upstreamArtifacts': [{
                    'paths': ['public/build/target.apk'],
                    'taskId': build_task_id,
                    'taskType': 'build',
                }]
            }
        })

    def _craft_base_task(self, name, extend_task):
        return {
            'taskGroupId': self.task_group_id,
            'schedulerId': 'taskcluster-github',
            'created': taskcluster.stringDate(datetime.datetime.now()),
            'deadline': taskcluster.stringDate(taskcluster.fromNow('1 day')),
            'metadata': {
                'name': name,
                'description': '',
                'owner': self.owner,
                'source': f'{self.repo_url}/raw/{self.commit}/.taskcluster.yml',
            },
            **extend_task
        }


def schedule_task_graph(ordered_tasks):
    queue = taskcluster.Queue({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})
    full_task_graph = {}

    for task_id, task in ordered_tasks:
        print("TASK", task_id)
        print(json.dumps(task, indent=4, separators=(',', ': ')))

        result = queue.createTask(task_id, task)
        print("RESULT", task_id)
        print(json.dumps(result))

        full_task_graph[task_id] = {
            # Some values of the task definition are automatically filled. Querying the task
            # allows to have the full definition. This is needed to make Chain of Trust happy
            'task': queue.task(task_id),
        }

    return full_task_graph
