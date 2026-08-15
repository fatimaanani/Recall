// Search method accent colors
export const SEARCH_METHOD_META = {
  exact_text: { label: "Text Search", swatch: "#93AF8F", className: "method-text" },
  semantic: { label: "Semantic Search", swatch: "#E0D3E6", className: "method-semantic" },
  speech_to_text: { label: "Speech-to-Text", swatch: "#97ACC2", className: "method-speech" },
};

// Profile (Settings pages)
export const mockCurrentUserProfile = {
  fullName: "Fatima Anani",
  username: "fatima",
  email: "fatima.anani@example.com",
  age: 23,
  gender: "female",
  status: "Student",
  avatarKey: "female",
  accountCreatedAt: "2026-04-11T10:24:00Z",
  lastLoginAt: "2026-07-11T20:47:00Z",
  emailVerified: true,
};

// Library
export const mockCollections = [
  { id: 1, name: "University", count: 7 },
  { id: 2, name: "Documentaries", count: 3 },
  { id: 3, name: "Anime", count: 5 },
  { id: 4, name: "Soundtracks", count: 4 },
  { id: 5, name: "Podcasts", count: 2 },
];

export const mockQuickFilters = [
  { id: "processed", label: "Processed", count: 18 },
  { id: "processing", label: "Processing", count: 3 },
  { id: "failed", label: "Failed", count: 1 },
  { id: "with_subtitles", label: "With Subtitles", count: 10 },
  { id: "without_subtitles", label: "Without Subtitles", count: 14 },
];

export const mockVideos = [
  { id: 1, title: "DSA Lecture - Week 6.mp4", collection: "University / DSA", mediaType: "video", durationLabel: "01:18:42", dateAddedLabel: "May 8, 2026", status: "ready", visibility: "private", sourceType: "user_upload", hasSubtitles: true },
  { id: 2, title: "Nature Documentary.mp4", collection: "Documentaries", mediaType: "video", durationLabel: "00:45:10", dateAddedLabel: "May 6, 2026", status: "ready", visibility: "shared", sourceType: "admin_preloaded", hasSubtitles: true },
  { id: 3, title: "Astrophysics Lecture.mp4", collection: "University / Physics", mediaType: "video", durationLabel: "02:05:33", dateAddedLabel: "May 8, 2026", status: "ready", visibility: "private", sourceType: "user_upload", hasSubtitles: true },
  { id: 4, title: "lofi_study_mix.mp3", collection: "Study / Lo-fi", mediaType: "audio", durationLabel: "01:02:15", dateAddedLabel: "May 2, 2026", status: "ready", visibility: "private", sourceType: "user_upload", hasSubtitles: false },
  { id: 5, title: "Interstellar Main Theme.flac", collection: "Soundtracks", mediaType: "audio", durationLabel: "00:03:47", dateAddedLabel: "Apr 29, 2026", status: "ready", visibility: "shared", sourceType: "admin_preloaded", hasSubtitles: false },
  { id: 6, title: "Calculus Lecture 3.mp4", collection: "University / Calculus", mediaType: "video", durationLabel: "00:55:21", dateAddedLabel: "Apr 28, 2026", status: "processing", visibility: "private", sourceType: "user_upload", hasSubtitles: false },
  { id: 7, title: "City Timelapse.mp4", collection: "Stock Footage", mediaType: "video", durationLabel: "01:31:09", dateAddedLabel: "Apr 26, 2026", status: "ready", visibility: "shared", sourceType: "admin_preloaded", hasSubtitles: true },
  { id: 8, title: "Podcast Episode 12.mp3", collection: "Podcasts", mediaType: "audio", durationLabel: "00:10:08", dateAddedLabel: "Apr 25, 2026", status: "failed", visibility: "private", sourceType: "user_upload", hasSubtitles: false },
];

// Uploads
export const mockStorageUsage = {
  usedBytes: 22_900_000_000,
  limitBytes: 53_687_091_200,
};

// Upload Queue state -> label/color
export const UPLOAD_STATE_META = {
  uploading: { label: "Uploading", swatch: "#D4A5A5", className: "upload-state-uploading" },
  processing: { label: "Processing", swatch: "#97ACC2", className: "upload-state-processing" },
  subtitles: { label: "Generating Subtitles", swatch: "#E0D3E6", className: "upload-state-subtitles" },
  done: { label: "Processed Successfully", swatch: "#93AF8F", className: "upload-state-done" },
};

export const mockUploadQueue = [
  { id: 1, fileName: "DSA Lecture - Week 6.mp4", sizeLabel: "1.24 GB", type: "MP4", durationLabel: "01:18:42", state: "processing", stageLabel: "Extracting audio... (this may take a few minutes)", statusLabel: "Processing...", progressPercent: 68, done: false },
  { id: 2, fileName: "lofi_study_mix.mp3", sizeLabel: "89.6 MB", type: "MP3", durationLabel: "01:02:15", state: "subtitles", stageLabel: "Transcribing audio...", statusLabel: "Generating subtitles...", progressPercent: 45, done: false },
  { id: 3, fileName: "Physics Lecture - Chapter 3.mp4", sizeLabel: "512 MB", type: "MP4", durationLabel: "00:45:10", state: "done", stageLabel: "Indexed and ready to search", statusLabel: "Completed!", progressPercent: 100, done: true },
];

// Search history (Settings > Data Management, Home recent searches)
export const mockSearchHistory = [
  { id: 201, queryLabel: '"I\'ll protect you"', searchMethod: "exact_text", resultsFound: 12, searchedAtLabel: "May 15, 2026 at 10:32 AM" },
  { id: 202, queryLabel: "Audio: uploaded_voice_01.wav", searchMethod: "speech_to_text", resultsFound: 8, searchedAtLabel: "May 15, 2026 at 09:45 AM" },
  { id: 204, queryLabel: "battle against titan", searchMethod: "exact_text", resultsFound: 15, searchedAtLabel: "May 14, 2026 at 08:15 PM" },
  { id: 205, queryLabel: "Audio: lecture_part2.wav", searchMethod: "speech_to_text", resultsFound: 6, searchedAtLabel: "May 14, 2026 at 07:42 PM" },
  { id: 206, queryLabel: "wind blowing leaves", searchMethod: "semantic", resultsFound: 9, searchedAtLabel: "May 13, 2026 at 06:10 PM" },
];

// Results, one adaptive route, method drives color/badge/labels
export const mockSearchResults = [
  { id: 101, searchMethod: "semantic", matchPercent: 96, title: "Binary Search Trees - Introduction and Insertion", sourceLabel: "CS_Data_Structures_Lecture5.mp4", timeRangeLabel: "32:14 - 38:02", durationLabel: "5 min 48 sec", matchedText: "In this part, the doctor explains what a binary search tree is, the properties, and how insertion maintains the BST property.", videoId: 1 },
  { id: 102, searchMethod: "semantic", matchPercent: 89, title: "Example: Inserting 65 in a BST", sourceLabel: "CS_Data_Structures_Lecture5.mp4", timeRangeLabel: "38:03 - 41:27", durationLabel: "3 min 24 sec", matchedText: "Step-by-step insertion example. The professor inserts 65 and shows the tree update.", videoId: 1 },
  { id: 103, searchMethod: "exact_text", matchPercent: 98, title: "Naruto - Episode 14: The Number of Ninja", sourceLabel: "Naruto S01E14.mp4", timeRangeLabel: "00:12:35", durationLabel: null, matchedText: '"I\'ll become Hokage one day!"', videoId: 7 },
  { id: 104, searchMethod: "exact_text", matchPercent: 93, title: "Naruto - Episode 27: Impossible Dream", sourceLabel: "Naruto S01E27.mp4", timeRangeLabel: "00:17:08", durationLabel: null, matchedText: '"I\'ll become Hokage one day!"', videoId: 7 },
  { id: 105, searchMethod: "speech_to_text", matchPercent: 97, title: "Causes of Climate Change", sourceLabel: "voice_query_2026-07-08.wav", timeRangeLabel: "00:02:14", durationLabel: null, matchedText: "The primary causes include greenhouse gas emissions from burning fossil fuels...", videoId: 3 },
  { id: 106, searchMethod: "speech_to_text", matchPercent: 94, title: "Deforestation and Land Use Change", sourceLabel: "voice_query_2026-07-08.wav", timeRangeLabel: "00:04:38", durationLabel: null, matchedText: "When forests are cut down, they release stored carbon and lose their ability to absorb CO2...", videoId: 3 },
];

// Query meta bar, one per search method
export const mockQueryMetaByMethod = {
  exact_text: { sourceLabel: "Search Source", sourceValue: "Text", fileLabel: null, fileValue: null, queryLabel: '"I\'ll become Hokage one day!"' },
  semantic: { sourceLabel: "Uploaded File", sourceValue: "CS_Data_Structures_Lecture5.mp4", fileLabel: "Duration", fileValue: "1:28:47", queryLabel: '"binary search trees and how insertion works"' },
  speech_to_text: { sourceLabel: "Audio Input", sourceValue: "voice_query_2026-07-08.wav", fileLabel: "Duration", fileValue: "00:12", queryLabel: "Can you explain the main causes of climate change and its effects on our environment?" },
};

// Scene Viewer, single detailed scene
export const mockSceneClip = {
  resultId: 101,
  videoTitle: "DSA Lecture - Week 6.mp4",
  topic: "Binary Search Trees",
  episodeLabel: "Week 6 - Trees",
  timestampLabel: "00:18:42",
  totalDurationLabel: "01:18:42",
  matchScorePercent: 96,
  matchScoreLabel: "Excellent Match",
  searchMethod: "semantic",
  sourceLabel: "Uploaded File",
  sourceFileName: "DSA Lecture - Week 6.mp4",
  keyPoints: [
    "Definition of Binary Search Tree",
    "BST properties (left < root < right)",
    "Example construction",
    "Visual representation",
  ],
  transcriptExcerpt:
    "...so in a binary search tree, for any node, all the values in the left subtree are smaller than the node, and all the values in the right subtree are greater than the node...",
  transcriptHighlight: "binary search tree",
  transcriptTags: [
    { term: "binary search tree", count: 4 },
    { term: "insert", count: 3 },
    { term: "delete", count: 2 },
    { term: "traversal", count: 2 },
    { term: "complexity", count: 2 },
  ],
  timeline: [
    { label: "Introduction", timeLabel: "00:00:00", active: false },
    { label: "Data Structures Overview", timeLabel: "00:04:31", active: false },
    { label: "Trees", timeLabel: "00:10:05", active: false },
    { label: "Binary Search Trees", timeLabel: "00:16:30 - 00:21:45", active: true },
    { label: "BST Operations", timeLabel: "00:21:46", active: false },
    { label: "Examples & Practice", timeLabel: "00:25:39", active: false },
  ],
};

// Admin: User Management
export const mockAdminUsers = [
  { id: 1, fullName: "Jordan Avery", username: "jordan", email: "jordan@example.com", accountStatus: "active", storageUsedLabel: "8.4 GB", uploadCount: 4, createdAtLabel: "Apr 11, 2026", lastLoginLabel: "Jul 11, 2026" },
  { id: 2, fullName: "Priya Nair", username: "priya", email: "priya@example.com", accountStatus: "suspended", storageUsedLabel: "1.2 GB", uploadCount: 1, createdAtLabel: "May 2, 2026", lastLoginLabel: "Jun 30, 2026" },
  { id: 3, fullName: "Marcus Webb", username: "marcusw", email: "marcus@example.com", accountStatus: "active", storageUsedLabel: "14.7 GB", uploadCount: 9, createdAtLabel: "Mar 20, 2026", lastLoginLabel: "Jul 12, 2026" },
];

// Admin: Shared Dataset
export const mockSharedDatasetVideos = mockVideos.filter((v) => v.visibility === "shared");

// Admin: Analytics & Evaluation
export const mockOperationalStats = {
  dateRangeLabel: "May 1 - May 31, 2026",
  searchAccuracyPercent: 93.4,
  searchAccuracyDeltaLabel: "+4.7% vs Apr 1 - Apr 30",
  avgResponseTimeSecLabel: "0.41 sec",
  avgResponseTimeDeltaLabel: "-0.12 sec vs Apr 1 - Apr 30",
  mediaFilesIndexed: 247,
  mediaFilesDeltaLabel: "+32 vs Apr 1 - Apr 30",
  queriesProcessed: 18421,
  queriesDeltaLabel: "+2,156 vs Apr 1 - Apr 30",
};

// One row per search method
export const mockMethodPerformance = [
  { method: "exact_text", accuracy: 0.812, precision: 0.81, recall: 0.75, f1: 0.78 },
  { method: "semantic", accuracy: 0.934, precision: 0.92, recall: 0.89, f1: 0.90 },
  { method: "speech_to_text", accuracy: 0.86, precision: 0.83, recall: 0.80, f1: 0.81 },
];

export const mockQueryDistribution = [
  { method: "exact_text", count: 12516, percent: 68 },
  { method: "speech_to_text", count: 3872, percent: 21 },
];

export const mockPipelineHealth = {
  mediaProcessed: 263,
  mediaProcessedDeltaLabel: "+28 vs last month",
  subtitlesGenerated: 241,
  subtitlesGeneratedDeltaLabel: "+25 vs last month",
  clipsCreated: 1842,
  clipsCreatedDeltaLabel: "+210 vs last month",
  failedUploads: 8,
  failedUploadsDeltaLabel: "-3 vs last month",
};

export const mockEvaluationSummary = {
  bestPerformingMethod: "semantic",
  bestPerformingNote: "High semantic understanding improves result quality.",
  highestAccuracyMethod: "semantic",
  highestAccuracyNote: "Highest raw accuracy across the evaluation test set.",
  fastestMethod: "exact_text",
  fastestNote: "Ideal for quick exact phrase lookups.",
  testSetSizeLabel: "Evaluation is based on a ground-truth test set of 500 queries across all search types.",
  lastRunLabel: "Last evaluation run: May 31, 2026 at 11:45 PM",
};
