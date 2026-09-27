package dev.forevereden.launcher

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.IBinder
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.random.Random

class ForeverEdenVpnService : VpnService() {
    private val running = AtomicBoolean(false)
    private val sessions = ConcurrentHashMap<TcpKey, TcpSession>()
    private var vpnInterface: ParcelFileDescriptor? = null
    private var output: FileOutputStream? = null
    private val outputLock = Any()

    override fun onBind(intent: Intent?): IBinder? = super.onBind(intent)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startCapture()
            ACTION_STOP -> stopCapture()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() { stopCapture(); super.onDestroy() }

    private fun startCapture() {
        if (!running.compareAndSet(false, true)) return
        try {
            startForeground(NOTIFICATION_ID, notification("Capturing official profile response"))
            val addresses = OFFICIAL_HOSTS.flatMap { InetAddress.getAllByName(it).filterIsInstance<Inet4Address>() }.distinctBy { it.hostAddress }
            check(addresses.isNotEmpty()) { "Official API has no IPv4 address" }
            val builder = Builder().setSession("ForeverEden official profile capture").setMtu(1500).setMetered(false)
                .addAddress("10.80.0.2", 32).addAllowedApplication(ORIGINAL_PACKAGE)
            addresses.forEach { builder.addRoute(requireNotNull(it.hostAddress), 32) }
            vpnInterface = builder.establish() ?: error("Android did not establish the capture VPN")
            output = FileOutputStream(vpnInterface!!.fileDescriptor)
            thread(name = "forevereden-vpn", isDaemon = true) { packetLoop(vpnInterface!!) }
            publish("Capturing $ORIGINAL_PACKAGE through the local TLS bridge")
        } catch (error: Exception) {
            publish("Capture failed: ${error.message}")
            stopCapture()
        }
    }

    private fun stopCapture() {
        if (!running.getAndSet(false)) return
        sessions.values.forEach(TcpSession::close)
        sessions.clear()
        runCatching { vpnInterface?.close() }
        vpnInterface = null; output = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        publish("Capture stopped")
    }

    private fun packetLoop(descriptor: ParcelFileDescriptor) {
        val input = FileInputStream(descriptor.fileDescriptor)
        val packet = ByteArray(32767)
        while (running.get()) {
            val length = runCatching { input.read(packet) }.getOrElse { break }
            if (length <= 0) continue
            val ip = parseIpv4(packet, length) ?: continue
            if (ip.protocol != 6) continue
            runCatching { handleTcp(packet, ip) }.onFailure { publish("Packet skipped: ${it.message}") }
        }
    }

    private fun handleTcp(packet: ByteArray, ip: Ipv4Packet) {
        val tcp = parseTcp(packet, ip) ?: return
        val key = TcpKey(ip.source, tcp.sourcePort, ip.destination, tcp.destinationPort)
        if ((tcp.flags and TcpFlags.RST) != 0) { sessions.remove(key)?.close(); return }
        if ((tcp.flags and TcpFlags.SYN) != 0 && !sessions.containsKey(key)) { openSession(key, tcp); return }
        val session = sessions[key] ?: return
        if (tcp.payloadLength > 0) {
            session.writeFromClient(tcp.sequence, packet.copyOfRange(tcp.payloadOffset, tcp.payloadOffset + tcp.payloadLength))
            writePacket(session.buildAck())
        }
        if ((tcp.flags and TcpFlags.FIN) != 0) {
            session.clientNext = incrementSequence(tcp.sequence, tcp.payloadLength + 1)
            writePacket(session.buildAck()); writePacket(session.buildFin())
            sessions.remove(key)?.close()
        }
    }

    private fun openSession(key: TcpKey, tcp: TcpPacket) {
        val socket = Socket()
        protect(socket)
        try {
            check(key.remotePort == 443) { "Unexpected routed port ${key.remotePort}" }
            socket.tcpNoDelay = true
            socket.connect(InetSocketAddress("127.0.0.1", CAPTURE_PORT), CONNECT_TIMEOUT_MS)
            val session = TcpSession(key, socket, Random.nextLong().toUInt32(), incrementSequence(tcp.sequence, 1))
            sessions[key] = session
            writePacket(session.buildSynAck()); session.serverNext = incrementSequence(session.serverNext, 1)
            readServer(session)
        } catch (error: Exception) {
            runCatching { socket.close() }
            writePacket(buildTcpIpv4Packet(key.remoteIp, key.localIp, key.remotePort, key.localPort, 0,
                incrementSequence(tcp.sequence, 1), TcpFlags.RST or TcpFlags.ACK))
            publish("Capture bridge connection failed: ${error.message}")
        }
    }

    private fun readServer(session: TcpSession) {
        thread(name = "forevereden-tls", isDaemon = true) {
            val buffer = ByteArray(32 * 1024)
            try {
                val input = session.socket.getInputStream()
                while (running.get() && !session.closed.get()) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    var offset = 0
                    while (offset < read) {
                        val size = minOf(TCP_MSS, read - offset)
                        writePacket(session.buildServerData(buffer.copyOfRange(offset, offset + size)))
                        session.serverNext = incrementSequence(session.serverNext, size); offset += size
                    }
                }
                if (!session.closed.get()) writePacket(session.buildFin())
            } catch (_: Exception) {
            } finally { sessions.remove(session.key); session.close() }
        }
    }

    private fun writePacket(packet: ByteArray) = synchronized(outputLock) { runCatching { output?.write(packet) }; Unit }

    private fun notification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "ForeverEden capture", NotificationManager.IMPORTANCE_LOW))
        val pending = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL_ID).setContentTitle("ForeverEden Capture").setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_download_done).setContentIntent(pending).setOngoing(true).build()
    }

    private fun publish(message: String) {
        Log.i("ForeverEdenVpn", message)
        sendBroadcast(Intent(ACTION_STATUS).setPackage(packageName)
            .putExtra(EXTRA_MESSAGE, message), NodeListenerService.INTERNAL_PERMISSION)
    }

    companion object {
        const val ACTION_START = "dev.forevereden.launcher.capture.START"
        const val ACTION_STOP = "dev.forevereden.launcher.capture.STOP"
        const val ACTION_STATUS = "dev.forevereden.launcher.capture.STATUS"
        const val EXTRA_MESSAGE = "message"
        private const val ORIGINAL_PACKAGE = "games.wfs.anothereden"
        private val OFFICIAL_HOSTS = listOf("api-us.another-eden.games", "api-ap.another-eden.games", "api-eu.another-eden.games",
            "bn-payment.wrightflyer.net", "gl-payment.gree-apps.net")
        private const val CAPTURE_PORT = 28764
        private const val CONNECT_TIMEOUT_MS = 10_000
        private const val TCP_MSS = 1200
        private const val CHANNEL_ID = "forevereden_capture"
        private const val NOTIFICATION_ID = 7302
    }
}

private data class TcpKey(val localIp: Int, val localPort: Int, val remoteIp: Int, val remotePort: Int)

private class TcpSession(val key: TcpKey, val socket: Socket, var serverNext: Long, var clientNext: Long) {
    val closed = AtomicBoolean(false)
    fun writeFromClient(sequence: Long, payload: ByteArray) {
        if (sequence != clientNext) return
        socket.getOutputStream().apply { write(payload); flush() }
        clientNext = incrementSequence(clientNext, payload.size)
    }
    fun buildSynAck() = packet(TcpFlags.SYN or TcpFlags.ACK)
    fun buildAck() = packet(TcpFlags.ACK)
    fun buildServerData(payload: ByteArray) = packet(TcpFlags.PSH or TcpFlags.ACK, payload)
    fun buildFin() = packet(TcpFlags.FIN or TcpFlags.ACK)
    private fun packet(flags: Int, payload: ByteArray = ByteArray(0)) = buildTcpIpv4Packet(
        key.remoteIp, key.localIp, key.remotePort, key.localPort, serverNext, clientNext, flags, payload)
    fun close() { if (closed.compareAndSet(false, true)) runCatching { socket.close() } }
}

private fun Long.toUInt32(): Long = this and 0xffffffffL
