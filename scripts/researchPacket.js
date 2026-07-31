const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const args = parseArgs(process.argv.slice(2));

const seriesId = args.series || "SER-000002";
const firstIssueNumber = args.issue || nextIssueNumber(seriesId);
const packetCount = parsePositiveInteger(args.count || "1", "count");

const series = read("data/series.json").records.find((record) => record.id === seriesId);
if (!series) {
	console.error(`ERROR Unknown series id: ${seriesId}`);
	process.exit(1);
}

if (!firstIssueNumber) {
	console.error("ERROR Could not determine an issue number. Pass --issue N.");
	process.exit(1);
}

if (packetCount > 1 && !Number.isInteger(Number(firstIssueNumber))) {
	console.error("ERROR Batch packets require a numeric first issue number.");
	process.exit(1);
}

const firstIssueId = args.issueId || nextId("ISS", read("data/issues.json").records);
const firstArcId = args.arcId || nextId("ARC", read("data/storyArcs.json").records);

for (let offset = 0; offset < packetCount; offset += 1) {
	const issueNumber = packetIssueNumber(firstIssueNumber, offset);
	const issueId = addToId(firstIssueId, offset);
	const arcId = addToId(firstArcId, offset);
	printPacket({ series, seriesId, issueNumber, issueId, arcId });
}

function parseArgs(values) {
	const parsed = {};
	for (let index = 0; index < values.length; index += 1) {
		const value = values[index];
		if (!value.startsWith("--")) {
			continue;
		}
		parsed[value.slice(2)] = values[index + 1];
		index += 1;
	}
	return parsed;
}

function parsePositiveInteger(value, label) {
	const parsed = Number(value);
	if (!Number.isInteger(parsed) || parsed < 1) {
		console.error(`ERROR --${label} must be a positive integer.`);
		process.exit(1);
	}
	return parsed;
}

function read(relativePath) {
	return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function nextIssueNumber(seriesId) {
	const issues = read("data/issues.json").records
		.filter((issue) => issue.seriesId === seriesId)
		.map((issue) => Number(issue.issueNumber))
		.filter((value) => Number.isInteger(value));
	if (issues.length === 0) {
		return "1";
	}
	return String(Math.max(...issues) + 1);
}

function nextId(prefix, records) {
	const max = records.reduce((currentMax, record) => {
		const match = String(record.id || "").match(new RegExp(`^${prefix}-(\\d{6})$`));
		return match ? Math.max(currentMax, Number(match[1])) : currentMax;
	}, 0);
	return `${prefix}-${String(max + 1).padStart(6, "0")}`;
}

function addToId(id, increment) {
	const match = id.match(/^([A-Z]+)-(\d{6})$/);
	if (!match) {
		return id;
	}
	return `${match[1]}-${String(Number(match[2]) + increment).padStart(6, "0")}`;
}

function packetIssueNumber(firstIssueNumber, offset) {
	if (!Number.isInteger(Number(firstIssueNumber))) {
		return firstIssueNumber;
	}
	return String(Number(firstIssueNumber) + offset);
}

function printPacket(packet) {
	const title = `${packet.series.title} #${packet.issueNumber}`;
	const marvelQuery = encodeURIComponent(`${title} Marvel official release date`);
	const gcdQuery = encodeURIComponent(`GCD ${title} on-sale date`);
	const readingQuery = encodeURIComponent(`${title} story arc reading order Spider-Man`);

	console.log(`# Research Packet: ${title}`);
	console.log("");
	console.log("## Searches");
	console.log("");
	console.log(`- Marvel: https://www.google.com/search?q=${marvelQuery}`);
	console.log(`- GCD: https://www.google.com/search?q=${gcdQuery}`);
	console.log(`- Story arc/order: https://www.google.com/search?q=${readingQuery}`);
	console.log("");
	console.log("## Needed Facts");
	console.log("");
	console.log("- issue release date");
	console.log("- story arc title");
	console.log("- story arc start date");
	console.log("");
	console.log("## Issue");
	console.log("");
	printJson({
		id: packet.issueId,
		seriesId: packet.seriesId,
		issueNumber: String(packet.issueNumber),
		releaseDate: null,
		releaseDatePrecision: "unknown",
		continuityId: packet.series.continuityId,
		leadCharacterIds: packet.series.leadCharacterIds,
		storyArcIds: [packet.arcId]
	});
	console.log("");
	console.log("## Story Arc");
	console.log("");
	printJson({
		id: packet.arcId,
		title,
		continuityId: packet.series.continuityId,
		startDate: null,
		startDatePrecision: "unknown",
		issueIds: [packet.issueId],
		orderedIssueIds: [packet.issueId]
	});
	console.log("");
}

function printJson(value) {
	console.log("```json");
	console.log(JSON.stringify(value, null, "\t"));
	console.log("```");
}
