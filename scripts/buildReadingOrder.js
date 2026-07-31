const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const seriesRecords = read("data/series.json").records;
const issueRecords = read("data/issues.json").records;
const arcRecords = read("data/storyArcs.json").records;
const universeRecords = read("data/universes.json").records;

const seriesById = indexById(seriesRecords);
const issueById = indexById(issueRecords);
const universeById = indexById(universeRecords);

const publicationOrder = issueRecords
	.slice()
	.sort(compareIssuesByReleaseDate)
	.map((issue) => issue.id);

const recommendedOrder = arcRecords
	.slice()
	.sort(compareArcsByStartDate)
	.flatMap((arc) => orderedIssuesForArc(arc).map((issue) => issue.id));

const readingList = arcRecords
	.slice()
	.sort(compareArcsByStartDate)
	.flatMap((arc) => orderedIssuesForArc(arc).map((issue) => readingListEntry(arc, issue)));

console.log(
	JSON.stringify(
		{
			sortRule: "storyArc.startDate, then issue.releaseDate",
			publicationOrder,
			recommendedOrder,
			readingList
		},
		null,
		"\t"
	)
);

function read(relativePath) {
	return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function indexById(records) {
	return new Map(records.map((record) => [record.id, record]));
}

function orderedIssuesForArc(arc) {
	const orderedIds = Array.isArray(arc.orderedIssueIds) && arc.orderedIssueIds.length > 0 ? arc.orderedIssueIds : arc.issueIds;
	const orderedIssues = orderedIds.map((issueId) => issueById.get(issueId)).filter(Boolean);
	return orderedIssues.slice().sort(compareIssuesByReleaseDate);
}

function readingListEntry(arc, issue) {
	const series = seriesById.get(issue.seriesId);
	const universe = universeById.get(issue.continuityId);

	return {
		comicRun: series ? series.title : issue.seriesId,
		issueNumber: issue.issueNumber,
		issueReleaseDate: issue.releaseDate,
		comicRunStartDate: series ? series.startDate : null,
		comicRunEndDate: series ? series.endDate : null,
		universe: universe ? universe.displayName || universe.name : issue.continuityId,
		mainCharacters: issue.leadCharacterIds || (series ? series.leadCharacterIds : []),
		storyArc: arc.title,
		storyArcStartDate: arc.startDate
	};
}

function compareArcsByStartDate(left, right) {
	return compareDates(left.startDate, right.startDate)
		|| compareStrings(left.title, right.title)
		|| compareStrings(left.id, right.id);
}

function compareIssuesByReleaseDate(left, right) {
	const leftSeries = seriesById.get(left.seriesId);
	const rightSeries = seriesById.get(right.seriesId);

	return compareDates(left.releaseDate, right.releaseDate)
		|| compareStrings(leftSeries ? leftSeries.title : left.seriesId, rightSeries ? rightSeries.title : right.seriesId)
		|| compareIssueNumbers(left.issueNumber, right.issueNumber)
		|| compareStrings(left.id, right.id);
}

function compareDates(left, right) {
	if (!left && !right) {
		return 0;
	}
	if (!left) {
		return 1;
	}
	if (!right) {
		return -1;
	}
	return left.localeCompare(right);
}

function compareIssueNumbers(left, right) {
	const leftNumber = Number(left);
	const rightNumber = Number(right);
	if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftNumber !== rightNumber) {
		return leftNumber - rightNumber;
	}
	return String(left).localeCompare(String(right), undefined, { numeric: true });
}

function compareStrings(left, right) {
	return String(left || "").localeCompare(String(right || ""));
}
