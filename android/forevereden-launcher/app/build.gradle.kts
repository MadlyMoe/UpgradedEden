plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val repositoryRoot = rootProject.file("../..").canonicalFile
val libnodeRoot = providers.environmentVariable("FOREVEREDEN_LIBNODE_DIR")
    .map(::file).orElse(rootProject.file("../../../RevivalSide/kmp/app/libnode")).get().canonicalFile
require(file("$libnodeRoot/bin/arm64-v8a/libnode.so").isFile) {
    "Set FOREVEREDEN_LIBNODE_DIR to RevivalSide's vendored Node Mobile libnode directory."
}
val identityText = file("$repositoryRoot/forevereden/local-runtime-identity.json").readText()
val seedRelative = Regex("\"path\"\\s*:\\s*\"([^\"]*seed-[^\"]+\\.json)\"")
    .find(identityText)?.groupValues?.get(1)?.replace('\\', '/')
    ?: error("ForeverEden private seed is not published")
val generatedAssets = layout.buildDirectory.dir("generated/forevereden-assets")
val prepareRuntimeAssets by tasks.registering(Sync::class) {
    into(generatedAssets.map { it.dir("runtime") })
    from("$repositoryRoot/tools") {
        include("forevereden_transport.cjs", "forevereden_capture_proxy.cjs", "forevereden_save.cjs", "forevereden_mobile_server.cjs",
            "forevereden_lottery_3_17_0.bin", "forevereden_rewards_3_17_0.bin")
    }
    from("$repositoryRoot/$seedRelative") { rename { "seed.json" } }
    from("$repositoryRoot/data/forevereden-evidence/private-login/body-codec-inputs.json") { rename { "codec.json" } }
    from("$repositoryRoot/data/forevereden-evidence/private-resources") {
        include("project.manifest.*.json", "version.manifest.*.json")
        into("resources")
    }
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
android {
    namespace = "dev.forevereden.launcher"
    compileSdk = 36
    ndkVersion = "27.2.12479018"
    defaultConfig {
        applicationId = "dev.forevereden.launcher"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        ndk { abiFilters += "arm64-v8a" }
        externalNativeBuild { cmake { arguments += listOf("-DNODE_ROOT=${libnodeRoot.invariantSeparatorsPath}", "-DANDROID_STL=c++_shared") } }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    externalNativeBuild { cmake { path = file("CMakeLists.txt") } }
    sourceSets.getByName("main") {
        jniLibs.srcDir(file("$libnodeRoot/bin"))
        assets.srcDir(generatedAssets)
    }
    packaging { jniLibs { useLegacyPackaging = true } }
}
tasks.named("preBuild").configure { dependsOn(prepareRuntimeAssets) }
