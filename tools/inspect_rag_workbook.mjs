import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/YinCh/xwechat_files/wxid_c8nfhei6rb2c22_2008/temp/RWTemp/2026-07/1e4c78e2baf14982b0c464517b483f80/心理gal表单(1).xlsx";
const outputDir = "tmp/rag-workbook-inspect";
await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 10000 });
await fs.writeFile(`${outputDir}/sheets.ndjson`, sheets.ndjson, "utf8");
const summary = await workbook.inspect({ kind: "workbook,sheet,region", maxChars: 30000, tableMaxRows: 120, tableMaxCols: 20, tableMaxCellChars: 500 });
await fs.writeFile(`${outputDir}/summary.ndjson`, summary.ndjson, "utf8");

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  const name = sheet.name.replace(/[\\/:*?"<>|]/g, "_");
  const values = used ? used.values : [];
  await fs.writeFile(`${outputDir}/${name}.json`, JSON.stringify(values, null, 2), "utf8");
  const preview = await workbook.render({ sheetName: sheet.name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
console.log(JSON.stringify({ outputDir, sheetNames: workbook.worksheets.items.map((sheet) => sheet.name) }));
