package uistatic

import "embed"

//go:embed static/index.html static/style.css static/app.js
var Files embed.FS
