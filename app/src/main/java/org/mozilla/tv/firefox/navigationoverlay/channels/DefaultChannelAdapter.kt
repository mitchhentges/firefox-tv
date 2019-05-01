/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.tv.firefox.navigationoverlay.channels

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import org.mozilla.tv.firefox.R
import org.mozilla.tv.firefox.channel.ChannelTile

class DefaultChannelAdapter : RecyclerView.Adapter<DefaultChannelTileViewHolder>() {

    private var tiles: List<ChannelTile> = emptyList()

    fun setTiles(tiles: List<ChannelTile>) {
        // todo; this
        this.tiles = tiles
        // todo: notify changed; Use the adapter that uses DiffUtil under the hood (in RecyclerView androidx lib?)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): DefaultChannelTileViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val view = inflater.inflate(R.layout.default_channel_tile, parent, false)
        return DefaultChannelTileViewHolder(view)
    }

    override fun getItemCount(): Int = tiles.size

    override fun onBindViewHolder(holder: DefaultChannelTileViewHolder, position: Int) {
        with(holder) {
            // todo: fill in tile
            tiles[position].setImage(imageView)
        }
    }

}

class DefaultChannelTileViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
    val titleView: TextView = itemView.findViewById(R.id.tileTitleView)
    val imageView: ImageView = itemView.findViewById(R.id.tileImageView)
}