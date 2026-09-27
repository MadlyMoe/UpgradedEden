package dev.forevereden.launcher

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import java.io.File
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class NodeListenerService : Service() {
    private val running = AtomicBoolean(false)
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); android.os.Process.killProcess(android.os.Process.myPid())
            return START_NOT_STICKY
        }
        val mode = intent?.getStringExtra(EXTRA_MODE).takeIf { it == MODE_CAPTURE } ?: MODE_PRIVATE
        val profile = intent?.getStringExtra(EXTRA_PROFILE).orEmpty()
        if (!running.compareAndSet(false, true)) { publish("Listener already running"); return START_STICKY }
        startForeground(NOTIFICATION_ID, notification("Preparing $mode server"))
        thread(name = "forevereden-node", isDaemon = true) { startNode(mode, profile) }
        return START_STICKY
    }

    private fun startNode(mode: String, profile: String) {
        try {
            check(NodeMobileBridge.isLoaded()) { NodeMobileBridge.loadErrorMessage() }
            val runtime = File(filesDir, "runtime")
            copyAssets("runtime", runtime)
            val root = File(filesDir, "forevereden").apply { mkdirs() }
            File(root, "listener-status.json").delete()
            thread(name = "forevereden-ready", isDaemon = true) {
                repeat(120) {
                    if (File(root, "listener-status.json").isFile) {
                        val label = if (mode == MODE_CAPTURE) "Capture server ready on 127.0.0.1:28764" else "Private server ready on 127.0.0.1:28765"
                        publish(label); getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(label)); return@thread
                    }
                    Thread.sleep(250)
                }
                publish("Listener readiness timed out")
            }
            publish("Starting $mode server")
            val args = mutableListOf("node", File(runtime, "main.cjs").absolutePath, mode, root.absolutePath)
            if (mode == MODE_PRIVATE && profile.isNotBlank()) args += profile
            val code = NodeMobileBridge.startNodeWithArguments(args.toTypedArray())
            publish("Listener exited with code $code")
        } catch (error: Throwable) {
            publish("Listener failed: ${error.message ?: error.javaClass.simpleName}")
        } finally { running.set(false); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
    }

    private fun copyAssets(assetPath: String, destination: File) {
        val children = assets.list(assetPath).orEmpty()
        if (children.isEmpty()) {
            destination.parentFile?.mkdirs(); assets.open(assetPath).use { input -> destination.outputStream().use(input::copyTo) }
        } else { destination.mkdirs(); children.forEach { copyAssets("$assetPath/$it", File(destination, it)) } }
    }

    private fun notification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "ForeverEden listener", NotificationManager.IMPORTANCE_LOW))
        val pending = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL_ID).setContentTitle("ForeverEden").setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_download_done).setContentIntent(pending).setOngoing(true).build()
    }

    private fun publish(message: String) {
        File(filesDir, "forevereden-listener.log").appendText("${Instant.now()} $message\n")
        sendBroadcast(Intent(ACTION_STATUS).setPackage(packageName).putExtra(EXTRA_MESSAGE, message), INTERNAL_PERMISSION)
    }

    companion object {
        const val MODE_CAPTURE = "capture"
        const val MODE_PRIVATE = "private"
        const val ACTION_START = "dev.forevereden.launcher.listener.START"
        const val ACTION_STOP = "dev.forevereden.launcher.listener.STOP"
        const val ACTION_STATUS = "dev.forevereden.launcher.listener.STATUS"
        const val EXTRA_MODE = "mode"
        const val EXTRA_PROFILE = "profile"
        const val EXTRA_MESSAGE = "message"
        const val INTERNAL_PERMISSION = "dev.forevereden.launcher.INTERNAL_STATUS"
        private const val CHANNEL_ID = "forevereden_listener"
        private const val NOTIFICATION_ID = 7301
    }
}
