import fs from "fs";

const formatsPath = "./onlyoffice-docs-formats.json";
const readmePath = "./README.md";

const filterByAction = (formats, action) => {
  return formats.filter(format => format.actions.includes(action));
}

const filterByConvertToOOXML = (formats) => {
  return formats.filter(format => format.convert.some(type => ["docx", "xlsx", "pptx"].includes(type)) );
}

const groupByType = (formats) => {
  const grouped = {};

  for (const f of formats) {
    const type = f.type || "unknown";
    if (!grouped[type]) grouped[type] = [];
    grouped[type].push(f.name.toUpperCase());
  }

  for (const type in grouped) {
    grouped[type].sort();
  }

  return grouped;
};

const buildSection = (sectionName, data) => {
  let md = `**${sectionName}:**\n\n`;

  for (const [type, names] of Object.entries(data)) {
    md += `- **${type.toUpperCase()}**: ${names.join(", ")}\n`;
  }

  return md;
};

const updateSectionInReadme = (title, data) => {
  const regex = new RegExp(`(## ${title}\\s*[\\s\\S]*?)(?=\\n## |$)`, 'g');

  let readme = fs.readFileSync(readmePath, "utf8");

  if (regex.test(readme)) {
    readme = readme.replace(regex, `## ${title}\n\n${data}`);
  } else {
    if (!readme.endsWith("\n")) readme += "\n";
    readme += `\n## ${title}\n\n${data}`;
  }

  fs.writeFileSync(readmePath, readme, "utf8");
}

const formats = JSON.parse(fs.readFileSync(formatsPath, "utf8"));

const viewable = groupByType(filterByAction(formats, "view"));
const editable = groupByType(filterByAction(formats, "edit"));
const lossyEditable = groupByType(filterByAction(formats, "lossy-edit"));
const customFilterEditable = groupByType(filterByAction(formats, "customfilter"));
const reviewing = groupByType(filterByAction(formats, "review"));
const commenting = groupByType(filterByAction(formats, "comment"));
const filling = groupByType(filterByAction(formats, "fill"));
const encrypting = groupByType(filterByAction(formats, "encrypt"));
const convertableToOOXML = groupByType(filterByConvertToOOXML(formats));

const forViewing = buildSection("For viewing", viewable);
const forEditing = buildSection("For editing", editable);
const forLossyEditing = buildSection("For editing with possible loss of information", lossyEditable);
const forCustomFilterEditing = buildSection("For editing with custom filter", customFilterEditable);
const forReviewing = buildSection("For reviewing", reviewing);
const forCommenting = buildSection("For commenting", commenting);
const forFilling = buildSection("For filling", filling);
const forEncrypting = buildSection("For encrypting", encrypting);
const forConvertableToOOXML = buildSection("For converting to Office Open XML formats", convertableToOOXML);

const supportedFormatsInfo = forViewing + "\n" +
                             forEditing + "\n" +
                             forLossyEditing + "\n" +
                             forCustomFilterEditing + "\n" +
                             forReviewing + "\n" +
                             forCommenting + "\n" +
                             forFilling + "\n" +
                             forEncrypting + "\n" +
                             forConvertableToOOXML;

updateSectionInReadme("Supported formats", supportedFormatsInfo);

console.log("✅ Markdown updated:", readmePath);
