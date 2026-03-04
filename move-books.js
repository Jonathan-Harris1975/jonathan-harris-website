const fs = require("fs");
const path = require("path");

const bookDir = path.join(__dirname, "book");
const ebooksDir = path.join(__dirname, "ebooks");

if (!fs.existsSync(ebooksDir)) {
  fs.mkdirSync(ebooksDir);
}

const folders = fs.readdirSync(bookDir);

folders.forEach((folder) => {
  const src = path.join(bookDir, folder);
  const dest = path.join(ebooksDir, folder);

  if (fs.statSync(src).isDirectory()) {
    fs.renameSync(src, dest);
    console.log(`Moved: ${folder}`);
  }
});

console.log("All book folders moved to /ebooks/");
