#include <jni.h>
#include <cstring>
#include <string>
#include <vector>
#include "node.h"

extern "C" JNIEXPORT jint JNICALL
Java_dev_forevereden_launcher_NodeMobileBridge_startNodeWithArguments(JNIEnv* env, jclass, jobjectArray arguments) {
    const jsize count = env->GetArrayLength(arguments);
    std::vector<std::string> storage;
    storage.reserve(static_cast<size_t>(count));
    size_t bytes = 0;
    for (jsize i = 0; i < count; ++i) {
        auto value = static_cast<jstring>(env->GetObjectArrayElement(arguments, i));
        const char* text = env->GetStringUTFChars(value, nullptr);
        storage.emplace_back(text == nullptr ? "" : text);
        if (text != nullptr) env->ReleaseStringUTFChars(value, text);
        env->DeleteLocalRef(value);
        bytes += storage.back().size() + 1;
    }
    std::vector<char> block(bytes == 0 ? 1 : bytes);
    std::vector<char*> argv(static_cast<size_t>(count));
    char* cursor = block.data();
    for (jsize i = 0; i < count; ++i) {
        const auto& value = storage[static_cast<size_t>(i)];
        std::memcpy(cursor, value.c_str(), value.size());
        cursor[value.size()] = '\0'; argv[static_cast<size_t>(i)] = cursor; cursor += value.size() + 1;
    }
    return static_cast<jint>(node::Start(static_cast<int>(count), argv.data()));
}
