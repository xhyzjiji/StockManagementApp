package com.example.stockmanagementsystem

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import com.example.stockmanagementsystem.databinding.FragmentHomeBinding

/** app 首页：功能介绍 + 使用说明书 */
class HomeFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        val vb = FragmentHomeBinding.inflate(inflater, container, false)
        vb.btnGotoWarehouse.setOnClickListener {
            (activity as? HomeShellActivity)?.navigateToTab(R.id.nav_warehouse)
        }
        return vb.root
    }
}
