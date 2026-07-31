const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const datasets = {
	series: read("data/series.json"),
	issues: read("data/issues.json"),
	storyArcs: read("data/storyArcs.json"),
	readingBlocks: read("data/readingBlocks.json"),
	events: read("data/events.json"),
	universes: read("data/universes.json"),
	sources: read("data/sources.json"),
	review: read("data/review.json")
};

console.log("Spider-Man JSON Database Audit");
console.log("");
for (const [name, dataset] of Object.entries(datasets)) {
	console.log(`${name}: ${dataset.records.length}`);
}

printCounts("Series by publication type", datasets.series.records, "publicationType");
printCounts("Series by verification status", datasets.series.records, "verificationStatus");
printCounts("Issues by type", datasets.issues.records, "issueType");
printCounts("Issues by reading style", datasets.issues.records, "readingStyle");
printCounts("Issues by verification status", datasets.issues.records, "verificationStatus");
printCounts("Review items by status", datasets.review.records, "status");

const openReview = datasets.review.records.filter((record) => record.status === "Open");
const issuesWithoutReleaseDates = datasets.issues.records.filter((record) => !record.releaseDate);
const issuesWithoutArcs = datasets.issues.records.filter((record) => !record.storyArcIds || record.storyArcIds.length === 0);
const arcsWithoutStartDates = datasets.storyArcs.records.filter((record) => !record.startDate);
const requiredBlocksWithoutOrder = datasets.readingBlocks.records.filter(
	(record) => record.readingStyle === "Required Interleave" && (!record.orderedIssueIds || record.orderedIssueIds.length === 0)
);

console.log("");
console.log(`Open review items: ${openReview.length}`);
console.log(`Issues without release dates: ${issuesWithoutReleaseDates.length}`);
console.log(`Issues without story arcs: ${issuesWithoutArcs.length}`);
console.log(`Story arcs without start dates: ${arcsWithoutStartDates.length}`);
console.log(`Required-interleave blocks without ordered issues: ${requiredBlocksWithoutOrder.length}`);

function read(relativePath) {
	return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function printCounts(title, records, field) {
	const counts = new Map();
	for (const record of records) {
		const value = record[field] ?? "Unspecified";
		counts.set(value, (counts.get(value) || 0) + 1);
	}
	console.log("");
	console.log(title);
	if (counts.size === 0) {
		console.log("- none");
		return;
	}
	for (const [value, count] of [...counts.entries()].sort()) {
		console.log(`- ${value}: ${count}`);
	}
}
