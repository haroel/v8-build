// Standalone runtime checks for the V8 15.7.112.23 Android monolith.
// This program uses embedded startup data and has no APK or Java dependency.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <unistd.h>

#include "libplatform/libplatform.h"
#include "v8.h"

namespace {
constexpr const char* kExpectedVersion = "15.7.112.23";
int passed_checks = 0;

bool Report(bool passed, const char* name) {
  std::printf("%s %s\n", passed ? "PASS" : "FAIL", name);
  std::fflush(stdout);
  if (passed) ++passed_checks;
  return passed;
}

void PrintException(v8::Isolate* isolate, v8::TryCatch& caught) {
  v8::String::Utf8Value exception(isolate, caught.Exception());
  std::fprintf(stderr, "V8 exception: %s\n",
               *exception ? *exception : "<unavailable>");
  if (!caught.StackTrace(isolate->GetCurrentContext()).IsEmpty()) {
    v8::Local<v8::Value> stack;
    if (caught.StackTrace(isolate->GetCurrentContext()).ToLocal(&stack)) {
      v8::String::Utf8Value text(isolate, stack);
      if (*text) std::fprintf(stderr, "%s\n", *text);
    }
  }
}

bool CheckJS(v8::Isolate* isolate, v8::Local<v8::Context> context,
             const char* name, const char* javascript) {
  v8::TryCatch caught(isolate);
  v8::Local<v8::String> source;
  v8::Local<v8::Script> script;
  v8::Local<v8::Value> value;
  if (!v8::String::NewFromUtf8(isolate, javascript).ToLocal(&source) ||
      !v8::Script::Compile(context, source).ToLocal(&script) ||
      !script->Run(context).ToLocal(&value)) {
    if (caught.HasCaught()) PrintException(isolate, caught);
    return Report(false, name);
  }
  if (!value->IsTrue()) {
    v8::String::Utf8Value actual(isolate, value);
    std::fprintf(stderr, "%s returned %s rather than true\n", name,
                 *actual ? *actual : "<unavailable>");
  }
  return Report(value->IsTrue(), name);
}

void NativeAdd(const v8::FunctionCallbackInfo<v8::Value>& args) {
  v8::Isolate* isolate = args.GetIsolate();
  if (args.Length() != 2 || !args[0]->IsNumber() || !args[1]->IsNumber()) {
    isolate->ThrowException(v8::Exception::TypeError(
        v8::String::NewFromUtf8Literal(isolate, "expected two numbers")));
    return;
  }
  v8::Local<v8::Context> context = isolate->GetCurrentContext();
  const double left = args[0]->NumberValue(context).FromMaybe(0);
  const double right = args[1]->NumberValue(context).FromMaybe(0);
  args.GetReturnValue().Set(v8::Number::New(isolate, left + right));
}

bool CheckCaughtException(v8::Isolate* isolate,
                          v8::Local<v8::Context> context) {
  v8::TryCatch caught(isolate);
  v8::Local<v8::Script> script;
  if (!v8::Script::Compile(
           context, v8::String::NewFromUtf8Literal(
                        isolate, "throw new Error('android-smoke-expected')"))
           .ToLocal(&script)) {
    return Report(false, "C++ catches JavaScript exception");
  }
  v8::Local<v8::Value> ignored;
  const bool threw = !script->Run(context).ToLocal(&ignored);
  if (!threw || !caught.HasCaught()) {
    return Report(false, "C++ catches JavaScript exception");
  }
  v8::String::Utf8Value message(isolate, caught.Exception());
  return Report(*message &&
                    std::strcmp(*message,
                                "Error: android-smoke-expected") == 0,
                "C++ catches JavaScript exception");
}

bool RunChecks(v8::Isolate* isolate) {
  v8::Isolate::Scope isolate_scope(isolate);
  v8::HandleScope handles(isolate);
  v8::Local<v8::Context> context = v8::Context::New(isolate);
  v8::Context::Scope context_scope(context);
  isolate->SetMicrotasksPolicy(v8::MicrotasksPolicy::kExplicit);

  if (!CheckJS(isolate, context, "arithmetic, functions, closures and hot loop", R"JS(
      (() => {
        const makeAdder = x => y => x + y;
        const factorial = n => n < 2 ? 1 : n * factorial(n - 1);
        let sum = 0;
        for (let i = 0; i < 10000; ++i) sum += i;
        const addPair = (a, b) => a + b;
        let warmSum = 0;
        for (let i = 0; i < 50000; ++i) warmSum += addPair(i, 1);
        return makeAdder(20)(22) === 42 && factorial(10) === 3628800 &&
               sum === 49995000 && warmSum === 1250025000;
      })()
  )JS")) return false;

  if (!CheckJS(isolate, context, "BigInt and Unicode", R"JS(
      (() => {
        const integer = (1n << 100n) + 12345n;
        const text = '\u4f60\u597dV8\u{1f680}';
        return BigInt(integer.toString()) === integer &&
               integer % 97n === 42n && text.length === 6 &&
               [...text].length === 5;
      })()
  )JS")) return false;

  v8::Local<v8::Function> callback;
  if (!v8::Function::New(context, NativeAdd).ToLocal(&callback) ||
      !context->Global()
           ->Set(context, v8::String::NewFromUtf8Literal(isolate, "nativeAdd"),
                 callback)
           .FromMaybe(false)) {
    return Report(false, "install C++ callback");
  }
  if (!CheckJS(isolate, context, "JavaScript calls C++ and catches native error",
               R"JS(
      (() => {
        if (nativeAdd(19, 23) !== 42) return false;
        try { nativeAdd('19', 23); return false; }
        catch (error) {
          return error instanceof TypeError &&
                 error.message === 'expected two numbers';
        }
      })()
  )JS")) return false;
  if (!CheckCaughtException(isolate, context)) return false;

  v8::Local<v8::ArrayBuffer> buffer = v8::ArrayBuffer::New(isolate, 32);
  std::shared_ptr<v8::BackingStore> backing = buffer->GetBackingStore();
  auto* bytes = static_cast<uint8_t*>(backing->Data());
  std::memset(bytes, 0, backing->ByteLength());
  bytes[0] = 42;
  if (!context->Global()
           ->Set(context,
                 v8::String::NewFromUtf8Literal(isolate, "nativeBuffer"),
                 buffer)
           .FromMaybe(false)) {
    return Report(false, "install native ArrayBuffer");
  }
  if (!CheckJS(isolate, context, "ArrayBuffer and typed-array interoperability",
               R"JS(
      (() => {
        const view = new Uint8Array(nativeBuffer);
        if (view.byteLength !== 32 || view[0] !== 42) return false;
        view[3] = 123;
        const words = new DataView(nativeBuffer);
        words.setUint32(8, 0x12345678, true);
        return words.getUint32(8, true) === 0x12345678 &&
               view[8] === 0x78 && view[11] === 0x12;
      })()
  )JS")) return false;
  if (!Report(bytes[3] == 123 && bytes[8] == 0x78 && bytes[11] == 0x12,
              "C++ observes JavaScript writes")) return false;

  if (!CheckJS(isolate, context, "Promise is queued until microtask checkpoint",
               R"JS(
      globalThis.promiseValue = 0;
      Promise.resolve(21).then(x => x * 2).then(x => { promiseValue = x; });
      promiseValue === 0
  )JS")) return false;
  isolate->PerformMicrotaskCheckpoint();
  if (!CheckJS(isolate, context, "Promise microtasks settle", R"JS(
      promiseValue === 42
  )JS")) return false;

  if (!CheckJS(isolate, context, "allocation and retained JavaScript state", R"JS(
      (() => {
        globalThis.retained = {token: 'survives-gc', values: [20, 22]};
        let checksum = 0;
        for (let n = 0; n < 10000; ++n) {
          const temporary = new Array(128).fill(n);
          checksum += temporary[0];
        }
        return checksum === 49995000;
      })()
  )JS")) return false;
  isolate->LowMemoryNotification();
  if (!CheckJS(isolate, context, "retained state and backing store survive GC",
               R"JS(
      retained.token === 'survives-gc' &&
      retained.values[0] + retained.values[1] === 42 &&
      new Uint8Array(nativeBuffer)[3] === 123
  )JS")) return false;

  if (!CheckJS(isolate, context, "WebAssembly compiles and executes", R"JS(
      (() => {
        if (typeof WebAssembly !== 'object') return false;
        // A module exporting answer(): i32 { return 42; }.
        const binary = new Uint8Array([
          0x00,0x61,0x73,0x6d,0x01,0x00,0x00,0x00,
          0x01,0x05,0x01,0x60,0x00,0x01,0x7f,
          0x03,0x02,0x01,0x00,
          0x07,0x0a,0x01,0x06,0x61,0x6e,0x73,0x77,0x65,0x72,0x00,0x00,
          0x0a,0x06,0x01,0x04,0x00,0x41,0x2a,0x0b
        ]);
        if (!WebAssembly.validate(binary)) return false;
        const compiled = new WebAssembly.Module(binary);
        return new WebAssembly.Instance(compiled).exports.answer() === 42;
      })()
  )JS")) return false;

  if (!CheckJS(isolate, context, "configured feature availability", R"JS(
      typeof Intl === 'undefined' && typeof Temporal === 'undefined'
  )JS")) return false;

  {
    v8::Local<v8::Context> other = v8::Context::New(isolate);
    v8::Context::Scope other_scope(other);
    if (!CheckJS(isolate, other, "contexts isolate JavaScript globals", R"JS(
        typeof retained === 'undefined' && typeof nativeAdd === 'undefined'
    )JS")) return false;
  }
  return true;
}
}  // namespace

int main(int argc, char** argv) {
  (void)argc;
  (void)argv;
  std::printf("V8 Android smoke test: version=%s pointer_bits=%zu page_size=%ld\n",
              v8::V8::GetVersion(), sizeof(void*) * 8, sysconf(_SC_PAGESIZE));
  if (!Report(std::strcmp(v8::V8::GetVersion(), kExpectedVersion) == 0,
              "exact V8 source version")) return 1;

  std::unique_ptr<v8::Platform> platform = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(platform.get());
  if (!v8::V8::Initialize()) {
    std::fprintf(stderr, "FAIL V8::Initialize\n");
    v8::V8::DisposePlatform();
    return 1;
  }
  std::unique_ptr<v8::ArrayBuffer::Allocator> allocator(
      v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams params;
  params.array_buffer_allocator = allocator.get();
  v8::Isolate* isolate = v8::Isolate::New(params);
  if (!isolate) {
    std::fprintf(stderr, "FAIL Isolate::New\n");
    v8::V8::Dispose();
    v8::V8::DisposePlatform();
    return 1;
  }
  const bool passed = RunChecks(isolate);
  isolate->Dispose();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  std::printf("%s: %d checks passed\n", passed ? "SUCCESS" : "FAILURE",
              passed_checks);
  return passed ? 0 : 1;
}
