package com.example.stockmanagementsystem

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.example.stockmanagementsystem.databinding.ActivityHomeShellBinding
import com.example.stockmanagementsystem.util.Insets

/** 底部导航宿主：app首页 / 我的仓库 / 我的作品 / 创作灵感 */
class HomeShellActivity : AppCompatActivity() {

    private lateinit var vb: ActivityHomeShellBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityHomeShellBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)

        // 直接持有 Fragment 实例：同一事务内 findFragmentByTag 查不到刚 add 的 Fragment
        supportFragmentManager.beginTransaction().apply {
            TAB_FRAGMENTS.forEach { (tabId, provider) ->
                var fragment = supportFragmentManager.findFragmentByTag(tabTag(tabId))
                if (fragment == null) {
                    fragment = provider()
                    add(R.id.fragmentContainer, fragment, tabTag(tabId))
                }
                if (tabId == R.id.nav_home) show(fragment) else hide(fragment)
            }
        }.commit()

        vb.bottomNav.setOnItemSelectedListener { item ->
            showTab(item.itemId)
            true
        }
        // 重选当前 tab：回到该 tab 的同时交给 fragment 自行刷新（这里仅保持选中态）
        vb.bottomNav.setOnItemReselectedListener { }
    }

    /** 供首页「进入我的仓库」等跳转复用 */
    fun navigateToTab(tabId: Int) {
        vb.bottomNav.selectedItemId = tabId
    }

    private fun showTab(tabId: Int) {
        val target = supportFragmentManager.findFragmentByTag(tabTag(tabId)) ?: return
        supportFragmentManager.beginTransaction().apply {
            TAB_FRAGMENTS.forEach { (id, _) ->
                supportFragmentManager.findFragmentByTag(tabTag(id))?.let { hide(it) }
            }
            show(target)
        }.commit()
    }

    private fun tabTag(tabId: Int) = "tab_$tabId"

    companion object {
        private val TAB_FRAGMENTS: List<Pair<Int, () -> Fragment>> = listOf(
            R.id.nav_home to { HomeFragment() },
            R.id.nav_warehouse to { WarehouseFragment() },
            R.id.nav_works to { PlaceholderFragment.newInstance(R.string.nav_works, R.drawable.ic_nav_works) },
            R.id.nav_inspiration to { PlaceholderFragment.newInstance(R.string.nav_inspiration, R.drawable.ic_nav_inspiration) },
        )
    }
}
