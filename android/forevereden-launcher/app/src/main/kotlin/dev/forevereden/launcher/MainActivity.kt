package dev.forevereden.launcher

import android.Manifest
import android.app.Activity
import android.content.ContentValues
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.SecureRandom

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var profiles: LinearLayout
    private val handler = Handler(Looper.getMainLooper())
    private var pendingCapture = false
    private var captureArmed = false
    private var capturing = false
    private var launchOfficialWhenVpnReady = false
    private var knownProfiles = emptyList<File>()
    private var launchWhenReady: String? = null
    private var pendingBackup: ByteArray? = null
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val message = intent.getStringExtra(NodeListenerService.EXTRA_MESSAGE)
                ?: intent.getStringExtra(ForeverEdenVpnService.EXTRA_MESSAGE) ?: return
            status.text = message
            if (message.startsWith("Capture server ready") && captureArmed) {
                startForegroundService(Intent(this@MainActivity, ForeverEdenVpnService::class.java)
                    .setAction(ForeverEdenVpnService.ACTION_START))
                captureArmed = false; launchOfficialWhenVpnReady = true
            } else if (message.startsWith("Capturing $ORIGINAL_PACKAGE") && launchOfficialWhenVpnReady) {
                launchOfficialWhenVpnReady = false; capturing = true
                packageManager.getLaunchIntentForPackage(ORIGINAL_PACKAGE)?.let(::startActivity)
                    ?: run { status.text = "$ORIGINAL_PACKAGE is not installed" }
            } else if (message.startsWith("Private server ready")) launchWhenReady?.let { packageName ->
                launchWhenReady = null
                packageManager.getLaunchIntentForPackage(packageName)?.let(::startActivity)
                    ?: run { status.text = "$packageName is not installed" }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
        val filter = IntentFilter().apply {
            addAction(NodeListenerService.ACTION_STATUS); addAction(ForeverEdenVpnService.ACTION_STATUS)
        }
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED)
        else @Suppress("DEPRECATION") registerReceiver(receiver, filter, NodeListenerService.INTERNAL_PERMISSION, null)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 44)
        pollProfiles()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        runCatching { unregisterReceiver(receiver) }
        super.onDestroy()
    }

    @Deprecated("VPN permission uses the platform result callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        when (requestCode) {
            VPN_REQUEST -> if (resultCode == RESULT_OK && pendingCapture) startCaptureServices()
                else { pendingCapture = false; status.text = "VPN permission was not granted" }
            EXPORT_REQUEST -> {
                val bytes = pendingBackup; pendingBackup = null
                if (resultCode == RESULT_OK && data?.data != null && bytes != null) runCatching {
                    contentResolver.openOutputStream(data.data!!, "w")!!.use { it.write(bytes) }
                }.onSuccess { status.text = "Profile backup exported" }
                    .onFailure { status.text = "Backup export failed: ${it.message}" }
            }
            IMPORT_REQUEST -> if (resultCode == RESULT_OK && data?.data != null) runCatching { readLimited(data.data!!) }
                .onSuccess(::importBackup).onFailure { status.text = "Backup import failed: ${it.message}" }
        }
    }

    private fun buildUi(): ScrollView {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(22), dp(28), dp(22), dp(28)); setBackgroundColor(0xff101827.toInt())
        }
        column.addView(TextView(this).apply {
            text = "ForeverEden"; textSize = 34f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
        })
        column.addView(TextView(this).apply {
            text = "Non-root profile capture and ARM64 private server"; textSize = 15f; setTextColor(0xffb8c5d9.toInt()); setPadding(0, 0, 0, dp(20))
        })
        status = label("Idle", 19f); column.addView(status)
        column.addView(label("USER MANAGER", 13f))
        profiles = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(profiles)
        column.addView(button("NEW LOCAL PROFILE") { createLocalProfile() })
        column.addView(button("RESET SELECTED PROFILE") { resetSelectedProfile() })
        column.addView(button("RESTORE LAST BACKUP") { restoreLastBackup() })
        column.addView(button("EXPORT SELECTED BACKUP") { exportSelectedProfile() })
        column.addView(button("IMPORT BACKUP") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json")
                .addCategory(Intent.CATEGORY_OPENABLE), IMPORT_REQUEST)
        })
        column.addView(button("INSTALL CAPTURE CERTIFICATE") { installCaptureCertificate() })
        column.addView(button("CAPTURE OFFICIAL PROFILE") { startCapture() })
        column.addView(button("START FOREVEREDEN") { startPrivate() })
        column.addView(button("STOP") { stopAll() })
        column.addView(TextView(this).apply {
            text = "Capture uses Android's VPN permission, reads only the official profile response, and stores a sanitized local copy. It does not transfer or migrate the official account."
            textSize = 13f; setTextColor(0xff94a3b8.toInt()); setPadding(0, dp(18), 0, 0)
        })
        return ScrollView(this).apply { isFillViewport = true; setBackgroundColor(0xff101827.toInt()); addView(column) }
    }

    private fun button(text: String, action: () -> Unit) = Button(this).apply {
        this.text = text; textSize = 15f; gravity = Gravity.CENTER; setOnClickListener { action() }
        layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(56)).apply { topMargin = dp(12) }
    }
    private fun label(text: String, size: Float) = TextView(this).apply { this.text = text; textSize = size; setTextColor(Color.WHITE); setPadding(0, dp(6), 0, dp(6)) }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun startCapture() {
        if (!installed(ORIGINAL_PACKAGE)) { status.text = "$ORIGINAL_PACKAGE is not installed"; return }
        pendingCapture = true
        val permission = VpnService.prepare(this)
        if (permission == null) startCaptureServices() else startActivityForResult(permission, VPN_REQUEST)
    }

    private fun installCaptureCertificate() {
        val certificate = assets.open("runtime/capture-ca.der").use { it.readBytes() }
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, "ForeverEden-Capture-CA.crt")
            put(MediaStore.Downloads.MIME_TYPE, "application/x-x509-ca-cert")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
        }
        val target = requireNotNull(contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values))
        contentResolver.openOutputStream(target, "w")!!.use { it.write(certificate) }
        status.text = "Certificate saved to Downloads. Choose CA certificate, then select ForeverEden-Capture-CA.crt."
        val installer = Intent().setClassName("com.android.settings", "com.android.settings.SubSettings")
            .putExtra(":settings:show_fragment", "com.android.settings.security.InstallCertificateFromStorage")
        runCatching { startActivity(installer) }
            .getOrElse { startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS)) }
    }

    private fun startCaptureServices() {
        pendingCapture = false; stopAll(); captureArmed = true
        handler.postDelayed({
            startForegroundService(Intent(this, NodeListenerService::class.java).setAction(NodeListenerService.ACTION_START)
                .putExtra(NodeListenerService.EXTRA_MODE, NodeListenerService.MODE_CAPTURE))
            status.text = "Starting non-root capture bridge"
        }, 800)
    }

    private fun startPrivate() {
        if (!installed(PRIVATE_PACKAGE)) { status.text = "$PRIVATE_PACKAGE is not installed"; return }
        stopAll(); launchWhenReady = PRIVATE_PACKAGE
        val selected = activeProfile()?.absolutePath.orEmpty()
        handler.postDelayed({
            startForegroundService(Intent(this, NodeListenerService::class.java).setAction(NodeListenerService.ACTION_START)
                .putExtra(NodeListenerService.EXTRA_MODE, NodeListenerService.MODE_PRIVATE)
                .putExtra(NodeListenerService.EXTRA_PROFILE, selected))
            status.text = "Starting private server"
        }, 800)
    }

    private fun stopAll() {
        startService(Intent(this, ForeverEdenVpnService::class.java).setAction(ForeverEdenVpnService.ACTION_STOP))
        startService(Intent(this, NodeListenerService::class.java).setAction(NodeListenerService.ACTION_STOP))
        captureArmed = false; capturing = false; launchOfficialWhenVpnReady = false; launchWhenReady = null
    }

    private fun pollProfiles() {
        val files = profileFiles()
        if (files.map { it.name } != knownProfiles.map { it.name }) {
            val captured = capturing && files.size > knownProfiles.size
            knownProfiles = files
            renderProfiles(files)
            if (captured) {
                capturing = false
                getPreferences(MODE_PRIVATE).edit().putString(ACTIVE_PROFILE, files.last().name).apply()
                renderProfiles(files)
                status.text = "Official profile saved in User Manager. Capture remains active until STOP."
            }
        }
        handler.postDelayed(::pollProfiles, 1500)
    }

    private fun renderProfiles(files: List<File>) {
        profiles.removeAllViews()
        val selected = getPreferences(MODE_PRIVATE).getString(ACTIVE_PROFILE, "").orEmpty()
        fun add(name: String, label: String) {
            profiles.addView(button((if (selected == name) "✓  " else "") + label) {
                getPreferences(MODE_PRIVATE).edit().putString(ACTIVE_PROFILE, name).apply()
                renderProfiles(files)
            })
        }
        add("", "Bundled starter profile")
        files.forEach { add(it.name, profileLabel(it)) }
    }

    private fun profileFiles(): List<File> = File(filesDir, "forevereden/profiles").listFiles()
        ?.filter { it.isFile && it.name.matches(Regex("forevereden-profile-[0-9a-f]{16}\\.json")) }
        ?.sortedBy(File::lastModified).orEmpty()

    private fun activeProfile(): File? {
        val name = getPreferences(MODE_PRIVATE).getString(ACTIVE_PROFILE, "").orEmpty()
        return profileFiles().firstOrNull { it.name == name }
    }

    private fun createLocalProfile() = runCatching {
        stopAll()
        val seed = assets.open("runtime/seed.json").bufferedReader().use { it.readText() }
        validateSeed(JSONObject(seed))
        val file = newProfileFile()
        writeAtomic(file, seed)
        getPreferences(MODE_PRIVATE).edit().putString(ACTIVE_PROFILE, file.name).apply()
        knownProfiles = profileFiles(); renderProfiles(knownProfiles)
        status.text = "New local profile created and selected"
    }.onFailure { status.text = "Profile creation failed: ${it.message}" }

    private fun resetSelectedProfile() {
        stopAll(); handler.postDelayed({ runCatching {
            val state = stateFile(activeProfile())
            if (!state.exists()) { status.text = "Selected profile is already at its starting state"; return@runCatching }
            val backups = File(filesDir, "forevereden/backups").apply { mkdirs() }
            val backup = File(backups, "${state.nameWithoutExtension}-${System.currentTimeMillis()}.json")
            state.copyTo(backup)
            check(state.delete()) { "Could not remove the current state" }
            status.text = "Selected profile reset; recovery copy saved"
        }.onFailure { status.text = "Profile reset failed: ${it.message}" } }, 800)
    }

    private fun exportSelectedProfile() {
        stopAll(); handler.postDelayed({ runCatching {
            val profile = activeProfile()
            val seed = JSONObject(profileSeedText(profile))
            validateSeed(seed)
            val state = stateFile(profile)
            val backup = JSONObject().put("format", BACKUP_FORMAT).put("version", 1).put("seed", seed)
                .put("state", if (state.exists()) JSONObject(state.readText()) else JSONObject.NULL)
            pendingBackup = backup.toString().toByteArray(Charsets.UTF_8)
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json")
                .addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE, "forevereden-profile-backup.json"), EXPORT_REQUEST)
        }.onFailure { status.text = "Backup preparation failed: ${it.message}" } }, 800)
    }

    private fun importBackup(text: String) = runCatching {
        stopAll()
        val backup = JSONObject(text)
        require(backup.optString("format") == BACKUP_FORMAT && backup.optInt("version") == 1) { "Unsupported backup format" }
        val seed = backup.getJSONObject("seed"); validateSeed(seed)
        val state = if (backup.isNull("state")) null else backup.getJSONObject("state").also { validateState(it, seed) }
        val file = newProfileFile()
        writeAtomic(file, seed.toString())
        try { if (state != null) writeAtomic(stateFile(file), state.toString()) } catch (error: Throwable) { file.delete(); throw error }
        getPreferences(MODE_PRIVATE).edit().putString(ACTIVE_PROFILE, file.name).apply()
        knownProfiles = profileFiles(); renderProfiles(knownProfiles)
        status.text = "Profile backup imported and selected"
    }.onFailure { status.text = "Backup import failed: ${it.message}" }

    private fun restoreLastBackup() {
        stopAll(); handler.postDelayed({ runCatching {
            val profile = activeProfile(); val state = stateFile(profile)
            val rolling = File("${state.absolutePath}.bak")
            val prefix = "${state.nameWithoutExtension}-"
            val saved = File(filesDir, "forevereden/backups").listFiles()
                ?.filter { it.isFile && it.name.startsWith(prefix) && it.extension == "json" }.orEmpty()
            val backup = (saved + listOfNotNull(rolling.takeIf(File::isFile))).maxByOrNull(File::lastModified)
                ?: error("No backup exists for the selected profile")
            val seed = JSONObject(profileSeedText(profile)); val restored = JSONObject(backup.readText())
            validateState(restored, seed)
            if (state.exists()) {
                val safety = File(filesDir, "forevereden/backups/${prefix}before-restore-${System.currentTimeMillis()}.json")
                safety.parentFile!!.mkdirs(); state.copyTo(safety)
            }
            writeAtomic(state, restored.toString())
            status.text = "Selected profile restored from its latest backup"
        }.onFailure { status.text = "Profile restore failed: ${it.message}" } }, 800)
    }

    private fun validateSeed(seed: JSONObject) {
        require(seed.optLong("user_id") > 0 && seed.optJSONObject("tables")?.length() == 207 &&
            seed.optJSONObject("token_aliases") != null) { "Invalid ForeverEden profile" }
    }

    private fun validateState(state: JSONObject, seed: JSONObject) {
        require(state.optInt("version") == 1 && state.optLong("user_id") == seed.optLong("user_id") &&
            state.optString("capability").matches(Regex("[0-9a-f]{32}")) && state.optString("aes_iv").length == 16 &&
            state.optJSONObject("replies") != null && state.optJSONObject("tables") != null) { "Invalid ForeverEden state" }
        val allowed = seed.getJSONObject("tables")
        val names = state.getJSONObject("tables").keys()
        while (names.hasNext()) require(allowed.has(names.next())) { "Backup contains an unknown profile table" }
    }

    private fun newProfileFile(): File {
        val random = ByteArray(8).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        return File(filesDir, "forevereden/profiles/forevereden-profile-$random.json")
    }

    private fun stateFile(profile: File?) = File(filesDir, "forevereden/private-state-${profile?.nameWithoutExtension ?: "seed"}.json")

    private fun profileSeedText(profile: File?) = if (profile == null)
        assets.open("runtime/seed.json").bufferedReader().use { it.readText() } else profile.readText()

    private fun writeAtomic(file: File, text: String) {
        file.parentFile!!.mkdirs()
        val temporary = File(file.parentFile, "${file.name}.tmp-${System.nanoTime()}")
        temporary.writeText(text + "\n")
        check(temporary.renameTo(file)) { "Could not publish ${file.name}" }
    }

    private fun readLimited(uri: android.net.Uri): String = contentResolver.openInputStream(uri)!!.use { input ->
        val output = ByteArrayOutputStream(); val buffer = ByteArray(8192)
        while (true) {
            val read = input.read(buffer); if (read < 0) break
            require(output.size() + read <= MAX_BACKUP_BYTES) { "Backup is too large" }
            output.write(buffer, 0, read)
        }
        output.toString(Charsets.UTF_8.name())
    }

    private fun profileLabel(file: File): String = runCatching {
        val seed = JSONObject(file.readText())
        val name = seed.getJSONObject("tables").getJSONObject("UserInfo").optString("name").takeUnless { it.isBlank() || it == "-" }
        "${name ?: "Captured profile"} • ${file.name.substringAfter("profile-").substringBefore('.')}"
    }.getOrDefault(file.name)

    private fun installed(name: String) = runCatching { packageManager.getApplicationInfo(name, 0) }.isSuccess

    companion object {
        private const val VPN_REQUEST = 91
        private const val ORIGINAL_PACKAGE = "games.wfs.anothereden"
        private const val PRIVATE_PACKAGE = "games.fed.anothereden"
        private const val ACTIVE_PROFILE = "active_profile"
        private const val BACKUP_FORMAT = "forevereden-profile-backup"
        private const val EXPORT_REQUEST = 92
        private const val IMPORT_REQUEST = 93
        private const val MAX_BACKUP_BYTES = 16 * 1024 * 1024
    }
}
