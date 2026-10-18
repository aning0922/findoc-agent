import { test } from "node:test";
import assert from "node:assert/strict";
import { excerptBlocks, verifiedTableVersion } from "../src/product/excerptBlocks.ts";
test("financial years and amounts retain the same columns, including blank cells", () => {
  const text = "单位：元\n| |项目|2024年|2023年|\n|---|---|---|---|\n| |营业收入|100|100|\n\n[1]";
  const blocks = excerptBlocks(text); const table = blocks[1]; assert.equal(table.kind, "table");
  if (table.kind === "table") { assert.deepEqual(table.header, ["", "项目", "2024年", "2023年"]); assert.deepEqual(table.rows[0], ["", "营业收入", "100", "100"]); }
  assert.equal(blocks[0].kind, "text"); assert.equal(blocks[2].kind, "text");
});
test("escape pipes, preserve unsafe text literally, and leave malformed rows visible", () => {
  const blocks = excerptBlocks("|项目|2025年|2024年|\n|---|---|---|\n|元\\|千元|0|-10|\n|bad|short|\n<script>evil()</script>");
  assert.equal(blocks[0].kind, "table");
  if (blocks[0].kind === "table") assert.deepEqual(blocks[0].rows[0], ["元|千元", "0", "-10"]);
  assert.deepEqual(blocks[1], {kind:"text", text:"|bad|short|\n<script>evil()</script>"});
});

test("legacy immutable Markdown stays literal and cannot acquire verified table presentation",()=>{
  const legacy="|项目||2024年|\n|---|---|---|\n|营业收入|100||";
  assert.deepEqual(excerptBlocks(legacy,false),[{kind:"text",text:legacy}]);
  assert.equal(verifiedTableVersion("fast-pdf-v2;pymupdf=1.28.0"),false);
  assert.equal(verifiedTableVersion(undefined),false);
  assert.equal(verifiedTableVersion("fast-pdf-v3;table-geometry-v1;pymupdf=1.28.0;pdfplumber=0.11.10"),false);
  assert.equal(verifiedTableVersion("fast-pdf-v4;table-geometry-v2;pymupdf=1.28.0;pdfplumber=0.11.10"),true);
});
