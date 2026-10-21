// Собирает сжатую ссылку для трипмастера: node tools/link.js legend.txt [plan.txt]
const fs = require("fs"), zlib = require("zlib");
const [legendFile, planFile] = process.argv.slice(2);
const data = {};
if (legendFile && legendFile !== "-") data.legend = fs.readFileSync(legendFile, "utf8").trim();
if (planFile) data.plan = fs.readFileSync(planFile, "utf8").trim();
const z = zlib.deflateRawSync(Buffer.from(JSON.stringify(data)), { level: 9 })
  .toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
console.log("https://yurikuchumov-ux.github.io/rally-tripmaster/#z=" + z);
