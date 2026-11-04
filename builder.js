/**
 * Check the platform configuration before generating the V8 build.
 * Keep platform settings in args.gn and leave upstream sources unchanged.
 */
const fs = require("fs");
const path = require("path");

const { V8_VERSION, PLATFORM, JOB_NAME, WORKSPACE, BUILD_TYPE } = process.env;

for (const [name, value] of Object.entries({ V8_VERSION, PLATFORM, JOB_NAME, WORKSPACE })) {
    if (!value) {
        throw new Error(`${name} must be set before running builder.js`);
    }
}

const versionHeaderPath = path.join(WORKSPACE, "v8", "include", "v8-version.h");
const versionHeader = fs.readFileSync(versionHeaderPath, "utf8");
const version = ["V8_MAJOR_VERSION", "V8_MINOR_VERSION", "V8_BUILD_NUMBER", "V8_PATCH_LEVEL"]
    .map((name) => {
        const match = versionHeader.match(new RegExp(`^#define\\s+${name}\\s+(\\d+)\\s*$`, "m"));
        if (!match) {
            throw new Error(`Missing ${name} in ${versionHeaderPath}`);
        }
        return match[1];
    })
    .join(".");
if (version !== V8_VERSION) {
    throw new Error(`V8 source version ${version} does not match V8_VERSION=${V8_VERSION}`);
}

if (JOB_NAME === "win" && !["release", "debug"].includes(BUILD_TYPE)) {
    throw new Error("BUILD_TYPE must be release or debug for Windows builds");
}
const suffix = JOB_NAME === "win" ? `.${BUILD_TYPE}` : "";
const argsPath = path.join(WORKSPACE, `args.${JOB_NAME}.${PLATFORM}${suffix}.gn`);
fs.accessSync(argsPath, fs.constants.R_OK);
console.log(`builder: V8 ${V8_VERSION}, ${JOB_NAME}/${PLATFORM}, ${argsPath}`);
