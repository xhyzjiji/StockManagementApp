package com.example.stockmanagementsystem

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.fragment.app.Fragment
import com.example.stockmanagementsystem.databinding.FragmentPlaceholderBinding

/** 「正在开发中」占位页 */
class PlaceholderFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        val vb = FragmentPlaceholderBinding.inflate(inflater, container, false)
        vb.textTitle.setText(requireArguments().getInt(ARG_TITLE))
        vb.imageIcon.setImageResource(requireArguments().getInt(ARG_ICON))
        return vb.root
    }

    companion object {
        private const val ARG_TITLE = "arg_title"
        private const val ARG_ICON = "arg_icon"

        fun newInstance(@StringRes title: Int, @DrawableRes icon: Int): PlaceholderFragment =
            PlaceholderFragment().apply {
                arguments = Bundle().apply {
                    putInt(ARG_TITLE, title)
                    putInt(ARG_ICON, icon)
                }
            }
    }
}
