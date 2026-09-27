package dev.forevereden.launcher

internal data class Ipv4Packet(
    val protocol: Int,
    val source: Int,
    val destination: Int,
    val headerLength: Int,
    val totalLength: Int,
)

internal data class TcpPacket(
    val sourcePort: Int,
    val destinationPort: Int,
    val sequence: Long,
    val acknowledgment: Long,
    val flags: Int,
    val headerLength: Int,
    val payloadOffset: Int,
    val payloadLength: Int,
)

internal data class UdpPacket(
    val sourcePort: Int,
    val destinationPort: Int,
    val length: Int,
    val payloadOffset: Int,
    val payloadLength: Int,
)

internal object TcpFlags {
    const val FIN = 0x01
    const val SYN = 0x02
    const val RST = 0x04
    const val PSH = 0x08
    const val ACK = 0x10
}

internal fun parseIpv4(packet: ByteArray, length: Int): Ipv4Packet? {
    if (length < 20) return null
    val version = (packet[0].toInt() ushr 4) and 0x0f
    if (version != 4) return null
    val headerLength = (packet[0].toInt() and 0x0f) * 4
    if (headerLength < 20 || length < headerLength) return null
    val totalLength = readU16(packet, 2).coerceAtMost(length)
    if (totalLength < headerLength) return null
    return Ipv4Packet(
        protocol = packet[9].toInt() and 0xff,
        source = readI32(packet, 12),
        destination = readI32(packet, 16),
        headerLength = headerLength,
        totalLength = totalLength,
    )
}

internal fun parseTcp(packet: ByteArray, ip: Ipv4Packet): TcpPacket? {
    if (ip.protocol != 6) return null
    val offset = ip.headerLength
    if (ip.totalLength < offset + 20) return null
    val headerLength = ((packet[offset + 12].toInt() ushr 4) and 0x0f) * 4
    if (headerLength < 20 || ip.totalLength < offset + headerLength) return null
    val payloadOffset = offset + headerLength
    return TcpPacket(
        sourcePort = readU16(packet, offset),
        destinationPort = readU16(packet, offset + 2),
        sequence = readU32(packet, offset + 4),
        acknowledgment = readU32(packet, offset + 8),
        flags = packet[offset + 13].toInt() and 0x3f,
        headerLength = headerLength,
        payloadOffset = payloadOffset,
        payloadLength = ip.totalLength - payloadOffset,
    )
}

internal fun parseUdp(packet: ByteArray, ip: Ipv4Packet): UdpPacket? {
    if (ip.protocol != 17) return null
    val offset = ip.headerLength
    if (ip.totalLength < offset + 8) return null
    val length = readU16(packet, offset + 4)
    if (length < 8 || ip.totalLength < offset + length) return null
    return UdpPacket(
        sourcePort = readU16(packet, offset),
        destinationPort = readU16(packet, offset + 2),
        length = length,
        payloadOffset = offset + 8,
        payloadLength = length - 8,
    )
}

internal fun buildTcpIpv4Packet(
    sourceIp: Int,
    destinationIp: Int,
    sourcePort: Int,
    destinationPort: Int,
    sequence: Long,
    acknowledgment: Long,
    flags: Int,
    payload: ByteArray = ByteArray(0),
): ByteArray {
    val ipHeaderLength = 20
    val tcpHeaderLength = 20
    val totalLength = ipHeaderLength + tcpHeaderLength + payload.size
    val out = ByteArray(totalLength)

    out[0] = 0x45
    out[1] = 0
    writeU16(out, 2, totalLength)
    writeU16(out, 4, 0)
    writeU16(out, 6, 0x4000)
    out[8] = 64
    out[9] = 6
    writeI32(out, 12, sourceIp)
    writeI32(out, 16, destinationIp)
    writeU16(out, 10, checksum(out, 0, ipHeaderLength))

    val tcpOffset = ipHeaderLength
    writeU16(out, tcpOffset, sourcePort)
    writeU16(out, tcpOffset + 2, destinationPort)
    writeU32(out, tcpOffset + 4, sequence)
    writeU32(out, tcpOffset + 8, acknowledgment)
    out[tcpOffset + 12] = (5 shl 4).toByte()
    out[tcpOffset + 13] = flags.toByte()
    writeU16(out, tcpOffset + 14, 65535)
    payload.copyInto(out, tcpOffset + tcpHeaderLength)
    writeU16(out, tcpOffset + 16, tcpChecksum(out, tcpOffset, tcpHeaderLength + payload.size, sourceIp, destinationIp))
    return out
}

internal fun buildUdpIpv4Packet(
    sourceIp: Int,
    destinationIp: Int,
    sourcePort: Int,
    destinationPort: Int,
    payload: ByteArray,
): ByteArray {
    val ipHeaderLength = 20
    val udpHeaderLength = 8
    val udpLength = udpHeaderLength + payload.size
    val totalLength = ipHeaderLength + udpLength
    val out = ByteArray(totalLength)
    out[0] = 0x45
    writeU16(out, 2, totalLength)
    writeU16(out, 6, 0x4000)
    out[8] = 64
    out[9] = 17
    writeI32(out, 12, sourceIp)
    writeI32(out, 16, destinationIp)
    writeU16(out, 10, checksum(out, 0, ipHeaderLength))

    val udpOffset = ipHeaderLength
    writeU16(out, udpOffset, sourcePort)
    writeU16(out, udpOffset + 2, destinationPort)
    writeU16(out, udpOffset + 4, udpLength)
    writeU16(out, udpOffset + 6, 0)
    payload.copyInto(out, udpOffset + udpHeaderLength)
    return out
}

internal fun readU16(bytes: ByteArray, offset: Int): Int {
    return ((bytes[offset].toInt() and 0xff) shl 8) or (bytes[offset + 1].toInt() and 0xff)
}

internal fun readU32(bytes: ByteArray, offset: Int): Long {
    return readI32(bytes, offset).toLong() and 0xffffffffL
}

internal fun readI32(bytes: ByteArray, offset: Int): Int {
    return ((bytes[offset].toInt() and 0xff) shl 24) or
        ((bytes[offset + 1].toInt() and 0xff) shl 16) or
        ((bytes[offset + 2].toInt() and 0xff) shl 8) or
        (bytes[offset + 3].toInt() and 0xff)
}

internal fun writeU16(bytes: ByteArray, offset: Int, value: Int) {
    bytes[offset] = ((value ushr 8) and 0xff).toByte()
    bytes[offset + 1] = (value and 0xff).toByte()
}

private fun writeU32(bytes: ByteArray, offset: Int, value: Long) {
    bytes[offset] = ((value ushr 24) and 0xff).toByte()
    bytes[offset + 1] = ((value ushr 16) and 0xff).toByte()
    bytes[offset + 2] = ((value ushr 8) and 0xff).toByte()
    bytes[offset + 3] = (value and 0xff).toByte()
}

private fun writeI32(bytes: ByteArray, offset: Int, value: Int) {
    bytes[offset] = ((value ushr 24) and 0xff).toByte()
    bytes[offset + 1] = ((value ushr 16) and 0xff).toByte()
    bytes[offset + 2] = ((value ushr 8) and 0xff).toByte()
    bytes[offset + 3] = (value and 0xff).toByte()
}

private fun checksum(bytes: ByteArray, offset: Int, length: Int): Int {
    var sum = 0L
    var index = offset
    val end = offset + length
    while (index + 1 < end) {
        sum += readU16(bytes, index).toLong()
        index += 2
    }
    if (index < end) sum += (bytes[index].toInt() and 0xff).toLong() shl 8
    while ((sum ushr 16) != 0L) sum = (sum and 0xffffL) + (sum ushr 16)
    return sum.inv().toInt() and 0xffff
}

private fun tcpChecksum(bytes: ByteArray, tcpOffset: Int, tcpLength: Int, sourceIp: Int, destinationIp: Int): Int {
    var sum = 0L
    sum += ((sourceIp ushr 16) and 0xffff).toLong()
    sum += (sourceIp and 0xffff).toLong()
    sum += ((destinationIp ushr 16) and 0xffff).toLong()
    sum += (destinationIp and 0xffff).toLong()
    sum += 6
    sum += tcpLength

    var index = tcpOffset
    val end = tcpOffset + tcpLength
    while (index + 1 < end) {
        sum += readU16(bytes, index).toLong()
        index += 2
    }
    if (index < end) sum += (bytes[index].toInt() and 0xff).toLong() shl 8
    while ((sum ushr 16) != 0L) sum = (sum and 0xffffL) + (sum ushr 16)
    return sum.inv().toInt() and 0xffff
}

internal fun incrementSequence(sequence: Long, amount: Int): Long = (sequence + amount) and 0xffffffffL
