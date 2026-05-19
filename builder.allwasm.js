
/**
/**
 * 用途：构建脚本相关的工具函数及流程控制
 * 本脚本ios构建包可以包含webassembly
 */

const fs = require("fs");
const path = require("path");

const trace = function (...args) {
    console.log("builder: ", ...args);
}


/**
 * 解析args.gn文件，返回一个对象
 * @param {*} argsPath args.gn文件路径
 * @returns 对象
 */
let parseGNArgs = function (argsPath, isToArray = false) {
    const content = fs.readFileSync(argsPath, "utf8");
    const lines = content.split("\n");
    let result = isToArray ? [] : {};
    const args = {};
    for (let line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.length === 0 || trimmedLine.startsWith("#")) {
            continue;
        }
        if (trimmedLine.includes("=")) {
            const [key, value] = trimmedLine.split("=");
            args[key] = value.trim();
        }
    }
    return args;
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
            const gnContent = fs.readFileSync(argsPath, "utf8");
            if (gnContent.indexOf(`v8_enable_drumbrake=true`) >= 0) {
                {
                    trace("v8_enable_drumbrake = true");
                    //  BUILD.gn
                    let gnPath = path.join(v8SourcePath, "BUILD.gn");
                    let content = fs.readFileSync(gnPath, "utf8");
                    const lines = content.split("\n");
                    let isModify = false;
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes("is_drumbrake_supported")) {
                            trace("********************************** Modify BUILD.gn:line-" + (i - 1));
                            lines[i - 1] = `# ${lines[i - 1]}`;
                            lines[i] = `# ${lines[i]}`;
                            lines[i + 1] = `# ${lines[i + 1]}`;
                            isModify = true;
                            break;
                        }
                    }
                    isModify && fs.writeFileSync(gnPath, lines.join("\n"));
                }
                {
                    // v8/gni/v8.gni
                    const codes = `      
      v8_enable_lite_mode = true
      # Since v8 has the Wasm interpreter mode with jitless, iOS enables it
      # to use WebAssembly.
      v8_enable_drumbrake = true
      v8_enable_webassembly = true

      # iOS doesn't use Turbofan.
      v8_enable_turbofan = false
`;
                    let gniPath = path.join(v8SourcePath, "gni", "v8.gni");
                    let content = fs.readFileSync(gniPath, "utf8");
                    const lines = content.split("\n");
                    let isModify = false;
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes("use_blink")) {
                            trace("********************************** Modify gni/v8.gn:line-" + (i));
                            lines[i] = lines[i] + codes;
                            isModify = true;
                            break;
                        }
                    }
                    isModify && fs.writeFileSync(gniPath, lines.join("\n"));
                }
            }
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