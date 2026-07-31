const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

const files = {
	series: { data: "data/series.json", schema: "schema/series.schema.json", pattern: /^SER-\d{6}$/ },
	issues: { data: "data/issues.json", schema: "schema/issues.schema.json", pattern: /^ISS-\d{6}$/ },
	storyArcs: { data: "data/storyArcs.json", schema: "schema/storyArcs.schema.json", pattern: /^ARC-\d{6}$/ },
	readingBlocks: { data: "data/readingBlocks.json", schema: "schema/readingBlocks.schema.json", pattern: /^BLK-\d{6}$/ },
	events: { data: "data/events.json", schema: "schema/events.schema.json", pattern: /^EVT-\d{6}$/ },
	universes: { data: "data/universes.json", schema: "schema/universes.schema.json", pattern: /^UNI-\d{6}$/ },
	sources: { data: "data/sources.json", schema: "schema/sources.schema.json", pattern: /^SRC-\d{6}$/ },
	review: { data: "data/review.json", schema: "schema/review.schema.json", pattern: /^REV-\d{6}$/ }
};

const errors = [];
const datasets = {};

for (const [name, config] of Object.entries(files)) {
	datasets[name] = readJson(config.data);
	readJson(config.schema);
	validateDatasetShape(name, datasets[name]);
	validateIds(name, datasets[name].records || [], config.pattern);
}

const indexes = Object.fromEntries(
	Object.entries(datasets).map(([name, dataset]) => [name, new Set((dataset.records || []).map((record) => record.id))])
);

validateReferences();
validateMinimalReadingListFields();
validateIssueCounts();
validateDuplicateIssueNumbers();
validateReadingOrders();

if (errors.length) {
	for (const error of errors) {
		console.error(`ERROR ${error}`);
	}
	process.exit(1);
}

console.log("Validation passed.");

function readJson(relativePath) {
	const filePath = path.join(root, relativePath);
	try {
		return JSON.parse(fs.readFileSync(filePath, "utf8"));
	} catch (error) {
		errors.push(`${relativePath}: ${error.message}`);
		return {};
	}
}

function validateDatasetShape(name, dataset) {
	if (typeof dataset.schemaVersion !== "string") {
		errors.push(`${name}: schemaVersion must be a string`);
	}
	if (typeof dataset.researchCutoff !== "string") {
		errors.push(`${name}: researchCutoff must be a string`);
	}
	if (!Array.isArray(dataset.records)) {
		errors.push(`${name}: records must be an array`);
	}
}

function validateIds(name, records, pattern) {
	const seen = new Set();
	for (const record of records) {
		if (!record || typeof record !== "object") {
			errors.push(`${name}: every record must be an object`);
			continue;
		}
		if (typeof record.id !== "string" || !pattern.test(record.id)) {
			errors.push(`${name}: invalid id ${record.id}`);
			continue;
		}
		if (seen.has(record.id)) {
			errors.push(`${name}: duplicate id ${record.id}`);
		}
		seen.add(record.id);
	}
}

function validateReferences() {
	for (const series of datasets.series.records) {
		checkId(series.continuityId, indexes.universes, `series ${series.id}.continuityId`);
		checkIds(series.issueIds, indexes.issues, `series ${series.id}.issueIds`);
		checkIds(series.sourceIds, indexes.sources, `series ${series.id}.sourceIds`);
		checkIds(series.reviewIds, indexes.review, `series ${series.id}.reviewIds`);
	}

	for (const issue of datasets.issues.records) {
		checkId(issue.seriesId, indexes.series, `issue ${issue.id}.seriesId`);
		checkId(issue.continuityId, indexes.universes, `issue ${issue.id}.continuityId`);
		checkIds(issue.storyArcIds, indexes.storyArcs, `issue ${issue.id}.storyArcIds`);
		checkIds(issue.readingBlockIds, indexes.readingBlocks, `issue ${issue.id}.readingBlockIds`);
		checkIds(issue.eventIds, indexes.events, `issue ${issue.id}.eventIds`);
		checkIds(issue.requiredBeforeIssueIds, indexes.issues, `issue ${issue.id}.requiredBeforeIssueIds`);
		checkIds(issue.recommendedBeforeIssueIds, indexes.issues, `issue ${issue.id}.recommendedBeforeIssueIds`);
		checkId(issue.continuedFromIssueId, indexes.issues, `issue ${issue.id}.continuedFromIssueId`, true);
		checkId(issue.continuesInIssueId, indexes.issues, `issue ${issue.id}.continuesInIssueId`, true);
		checkIds(issue.referencesIssueIds, indexes.issues, `issue ${issue.id}.referencesIssueIds`);
		checkIds(issue.sourceIds, indexes.sources, `issue ${issue.id}.sourceIds`);
		checkIds(issue.reviewIds, indexes.review, `issue ${issue.id}.reviewIds`);
	}

	for (const arc of datasets.storyArcs.records) {
		checkId(arc.continuityId, indexes.universes, `storyArc ${arc.id}.continuityId`);
		checkIds(arc.issueIds, indexes.issues, `storyArc ${arc.id}.issueIds`);
		checkIds(arc.orderedIssueIds, indexes.issues, `storyArc ${arc.id}.orderedIssueIds`);
		checkId(arc.eventId, indexes.events, `storyArc ${arc.id}.eventId`, true);
		checkId(arc.startIssueId, indexes.issues, `storyArc ${arc.id}.startIssueId`, true);
		checkId(arc.endIssueId, indexes.issues, `storyArc ${arc.id}.endIssueId`, true);
		checkIds(arc.sourceIds, indexes.sources, `storyArc ${arc.id}.sourceIds`);
		checkIds(arc.reviewIds, indexes.review, `storyArc ${arc.id}.reviewIds`);
	}

	for (const block of datasets.readingBlocks.records) {
		checkId(block.continuityId, indexes.universes, `readingBlock ${block.id}.continuityId`);
		checkIds(block.issueIds, indexes.issues, `readingBlock ${block.id}.issueIds`);
		checkIds(block.orderedIssueIds, indexes.issues, `readingBlock ${block.id}.orderedIssueIds`);
		checkId(block.eventId, indexes.events, `readingBlock ${block.id}.eventId`, true);
		checkIds(block.previousBlockIds, indexes.readingBlocks, `readingBlock ${block.id}.previousBlockIds`);
		checkIds(block.nextBlockIds, indexes.readingBlocks, `readingBlock ${block.id}.nextBlockIds`);
		checkIds(block.requiredBeforeBlockIds, indexes.readingBlocks, `readingBlock ${block.id}.requiredBeforeBlockIds`);
		checkIds(block.recommendedBeforeBlockIds, indexes.readingBlocks, `readingBlock ${block.id}.recommendedBeforeBlockIds`);
		checkIds(block.sourceIds, indexes.sources, `readingBlock ${block.id}.sourceIds`);
		checkIds(block.reviewIds, indexes.review, `readingBlock ${block.id}.reviewIds`);
	}

	for (const event of datasets.events.records) {
		checkIds(event.continuityIds, indexes.universes, `event ${event.id}.continuityIds`);
		for (const field of [
			"coreIssueIds",
			"requiredTieInIssueIds",
			"recommendedTieInIssueIds",
			"optionalTieInIssueIds",
			"orderedCoreReadingIds",
			"orderedCompleteReadingIds",
			"preludeIssueIds",
			"aftermathIssueIds"
		]) {
			checkIds(event[field], indexes.issues, `event ${event.id}.${field}`);
		}
		checkIds(event.sourceIds, indexes.sources, `event ${event.id}.sourceIds`);
		checkIds(event.reviewIds, indexes.review, `event ${event.id}.reviewIds`);
	}

	for (const universe of datasets.universes.records) {
		checkIds(universe.sourceIds, indexes.sources, `universe ${universe.id}.sourceIds`);
		checkIds(universe.reviewIds, indexes.review, `universe ${universe.id}.reviewIds`);
	}

	for (const review of datasets.review.records) {
		checkIds(review.sourceIds, indexes.sources, `review ${review.id}.sourceIds`);
	}
}

function validateIssueCounts() {
	const issuesBySeries = new Map();
	for (const issue of datasets.issues.records) {
		issuesBySeries.set(issue.seriesId, (issuesBySeries.get(issue.seriesId) || 0) + 1);
	}
	for (const series of datasets.series.records) {
		if (series.issueCount === undefined || series.issueCount === null) {
			continue;
		}
		const actual = issuesBySeries.get(series.id) || 0;
		if (series.issueCount !== actual) {
			errors.push(`series ${series.id}: issueCount ${series.issueCount} does not match ${actual} linked issues`);
		}
	}
}

function validateMinimalReadingListFields() {
	for (const series of datasets.series.records) {
		requireField(series, "title", `series ${series.id}`);
		requireField(series, "startDate", `series ${series.id}`);
		requireField(series, "startDatePrecision", `series ${series.id}`);
		requireField(series, "endDatePrecision", `series ${series.id}`);
		requireArray(series, "leadCharacterIds", `series ${series.id}`);
		requireField(series, "continuityId", `series ${series.id}`);
	}

	for (const issue of datasets.issues.records) {
		requireField(issue, "seriesId", `issue ${issue.id}`);
		requireField(issue, "issueNumber", `issue ${issue.id}`);
		requireField(issue, "releaseDate", `issue ${issue.id}`);
		requireField(issue, "releaseDatePrecision", `issue ${issue.id}`);
		requireField(issue, "continuityId", `issue ${issue.id}`);
		requireArray(issue, "leadCharacterIds", `issue ${issue.id}`);
		requireArray(issue, "storyArcIds", `issue ${issue.id}`);
	}

	for (const arc of datasets.storyArcs.records) {
		requireField(arc, "title", `storyArc ${arc.id}`);
		requireField(arc, "continuityId", `storyArc ${arc.id}`);
		requireField(arc, "startDate", `storyArc ${arc.id}`);
		requireField(arc, "startDatePrecision", `storyArc ${arc.id}`);
		requireArray(arc, "issueIds", `storyArc ${arc.id}`);
		requireArray(arc, "orderedIssueIds", `storyArc ${arc.id}`);
	}
}

function requireField(record, field, label) {
	if (record[field] === undefined || record[field] === null || record[field] === "") {
		errors.push(`${label}: missing required minimal field ${field}`);
	}
}

function requireArray(record, field, label) {
	if (!Array.isArray(record[field]) || record[field].length === 0) {
		errors.push(`${label}: ${field} must be a non-empty array`);
	}
}

function validateDuplicateIssueNumbers() {
	const seen = new Map();
	for (const issue of datasets.issues.records) {
		const key = `${issue.seriesId}::${String(issue.issueNumber).toLowerCase()}`;
		if (seen.has(key) && (!issue.notes || issue.notes.length === 0)) {
			errors.push(`issue ${issue.id}: duplicate issue number in series without notes`);
		}
		seen.set(key, issue.id);
	}
}

function validateReadingOrders() {
	checkUniqueOrder("publicationOrder");
	checkUniqueOrder("recommendedReadingOrder");
}

function checkUniqueOrder(field) {
	const seen = new Map();
	for (const issue of datasets.issues.records) {
		const value = issue[field];
		if (value === null || value === undefined) {
			continue;
		}
		if (seen.has(value)) {
			errors.push(`issues ${seen.get(value)} and ${issue.id}: duplicate ${field} ${value}`);
		}
		seen.set(value, issue.id);
	}
}

function checkIds(values, index, label) {
	if (values === undefined) {
		return;
	}
	if (!Array.isArray(values)) {
		errors.push(`${label} must be an array`);
		return;
	}
	const seen = new Set();
	for (const value of values) {
		if (seen.has(value)) {
			errors.push(`${label} contains duplicate id ${value}`);
		}
		seen.add(value);
		checkId(value, index, label);
	}
}

function checkId(value, index, label, nullable = false) {
	if (value === null && nullable) {
		return;
	}
	if (value === undefined || value === null) {
		return;
	}
	if (!index.has(value)) {
		errors.push(`${label} references missing id ${value}`);
	}
}
