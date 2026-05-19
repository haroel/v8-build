/**
 * 将.gn文件解析成一个对象, 键值对的形式，方便后续构建脚本使用
 * @param {*} argsContent 
 */
 function parseGnArgs(argsContent) {
    const lines = argsContent.split("\n");
    const result = new Map();
    for (let line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.length === 0 || trimmedLine.indexOf("#")>=0) {
            continue;
        }
        if (trimmedLine.includes("=")) {
            const [key, value] = trimmedLine.split("=");
            result.set(key, trimmedLine);
        }
    }
    return result;
}

// let result = parseGnArgs(require("fs").readFileSync("args.android.arm64.gn", "utf8"));
// console.log(result);

module.exports = parseGnArgs;