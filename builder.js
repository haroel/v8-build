
/**
/**
 * 用途：构建脚本相关的工具函数及流程控制
 */

const fs = require("fs");
const path = require("path");

const trace = function (...args) {
    console.log("builder: ", ...args);
}



const v8Version = process.env.V8_VERSION;
const platform = process.env.PLATFORM; // arm64|arm|x64
const jobName = process.env.JOB_NAME;  // android|ios|mac|win
const workspace = process.env.WORKSPACE;
const NDK_ROOT = process.env.NDK_ROOT;

trace("v8Version=" + v8Version);
trace("platform=" + platform);
trace("jobName=" + jobName);
trace("NDK_ROOT=" + NDK_ROOT);
trace("workspace=" + workspace);

const v8SourcePath = path.join(workspace, "v8");
const gnParser = require("./gn.parser.js");
/**
 * 在ninja构建前执行，修改v8源码
 */
let onBeforeBuild = function () {

    switch (jobName) {
        case "android": {
            const argsPath = path.join(workspace, `args.${jobName}.${platform}.gn`);
            const gnContent = fs.readFileSync(argsPath, "utf8");
            /**
             * android_ndk_root="${NDK_ROOT}"
clang_base_path="${NDK_ROOT}/toolchains/llvm/prebuilt/linux-x86_64"
             * 
             */
            let newGnContent = gnContent + 
`use_glib=false
`;
            fs.writeFileSync(argsPath, newGnContent);
            trace("**********************************************")
            trace(newGnContent);
            trace("**********************************************")
            break;
        }
        case "ios": {
            const argsPath = path.join(workspace, `args.${jobName}.${platform}.gn`);
            // 关闭ios的wasm以及drumbrake支持
            console.log("关闭ios的wasm以及drumbrake支持");
            let gnArgs = gnParser(fs.readFileSync(argsPath, "utf8"));
            gnArgs.set("v8_enable_webassembly", "v8_enable_webassembly=false");
            gnArgs.set("v8_enable_pointer_compression", "v8_enable_pointer_compression=false");
            gnArgs.set("cppgc_enable_caged_heap", "cppgc_enable_caged_heap=false");
            gnArgs.set("v8_enable_drumbrake", "v8_enable_drumbrake=false");
            fs.writeFileSync(argsPath, Array.from(gnArgs.values()).join("\n"));
            break;
        }

        case "mac":
            {
                // DO NOTHING
                break;
            }
        case "win":
            {
                // DO NOTHING
                break;
            }
    }
};
onBeforeBuild();
