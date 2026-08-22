package com.example.stockmanagementsystem

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.stockmanagementsystem.data.Repository
import com.example.stockmanagementsystem.util.Insets
import com.example.stockmanagementsystem.databinding.ActivityRecordListBinding
import com.example.stockmanagementsystem.ui.RecordAdapter
import com.example.stockmanagementsystem.util.runInBackground

/** 整个仓库的出入库流水（新→旧） */
class RecordListActivity : AppCompatActivity() {

    private lateinit var vb: ActivityRecordListBinding
    private val repo by lazy { Repository.get(this) }
    private lateinit var adapter: RecordAdapter
    private var warehouseId: Long = -1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vb = ActivityRecordListBinding.inflate(layoutInflater)
        setContentView(vb.root)
        Insets.apply(this)
        vb.toolbar.setNavigationOnClickListener { finish() }

        warehouseId = intent.getLongExtra(MainActivity.EXTRA_WAREHOUSE_ID, -1)
        if (warehouseId <= 0) {
            finish()
            return
        }

        adapter = RecordAdapter(showItemName = true)
        vb.recycler.layoutManager = LinearLayoutManager(this)
        vb.recycler.adapter = adapter
    }

    override fun onResume() {
        super.onResume()
        runInBackground({ repo.listRecordsForWarehouse(warehouseId) }) { list ->
            adapter.submit(list)
            vb.textEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    companion object {
        fun intent(context: Context, warehouseId: Long): Intent =
            Intent(context, RecordListActivity::class.java)
                .putExtra(MainActivity.EXTRA_WAREHOUSE_ID, warehouseId)
    }
}
