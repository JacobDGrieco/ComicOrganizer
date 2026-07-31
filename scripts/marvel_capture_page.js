#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

async function main() {
	const args = parseArgs(process.argv.slice(2));
	if (!args.url || !args.output) {
		throw new Error("Usage: node scripts/marvel_capture_page.js --url <url> --output <file> [--scroll]");
	}

	const browser = await chromium.launch({ headless: true });
	try {
		const page = await browser.newPage({
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
		});
		await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: 60000 });
		await page.waitForTimeout(2000);
		if (args.scroll) {
			await autoScroll(page);
		}
		await page.waitForTimeout(1000);
		const content = await page.content();
		const outputPath = path.resolve(args.output);
		fs.mkdirSync(path.dirname(outputPath), { recursive: true });
		fs.writeFileSync(outputPath, content, "utf8");
		console.error(`Captured ${args.url} -> ${outputPath}`);
	} finally {
		await browser.close();
	}
}

function parseArgs(argv) {
	const args = { scroll: false };
	for (let index = 0; index < argv.length; index += 1) {
		const arg = argv[index];
		if (arg === "--url") {
			args.url = argv[++index];
		} else if (arg === "--output") {
			args.output = argv[++index];
		} else if (arg === "--scroll") {
			args.scroll = true;
		} else {
			throw new Error(`Unknown argument: ${arg}`);
		}
	}
	return args;
}

async function autoScroll(page) {
	await page.evaluate(async () => {
		await new Promise((resolve) => {
			let totalHeight = 0;
			const distance = 700;
			const timer = setInterval(() => {
				const scrollHeight = document.body.scrollHeight;
				window.scrollBy(0, distance);
				totalHeight += distance;
				if (totalHeight >= scrollHeight) {
					clearInterval(timer);
					resolve();
				}
			}, 150);
		});
	});
}

main().catch((error) => {
	console.error(`ERROR ${error.message}`);
	process.exit(1);
});
