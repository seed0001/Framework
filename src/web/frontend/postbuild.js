import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const source = path.join(__dirname, '../static/index.html');
const dest = path.join(__dirname, '../templates/index.html');

try {
  if (fs.existsSync(source)) {
    const destDir = path.dirname(dest);
    if (!fs.existsSync(destDir)) {
      fs.mkdirSync(destDir, { recursive: true });
    }
    fs.renameSync(source, dest);
    console.log(`Successfully moved index.html to ${dest}`);
  } else {
    console.warn(`Source file not found: ${source}`);
  }
} catch (err) {
  console.error(`Error moving index.html: ${err.message}`);
  process.exit(1);
}
