// App templates shown in the Editor. Filtered by the selected runtime so
// a user picking "Node.js" only sees Node templates.
//
// When adding a language template, keep the code SHORT and self-contained
// and make sure it prints something useful — templates are the fastest
// way a new dev sanity-checks that their runtime works.

export interface AppTemplate {
  key: string;
  name: string;
  language: string;
  packages: string[];
  code: string;
}

export const APP_TEMPLATES: AppTemplate[] = [
  // ---------- Python ----------
  {
    key: 'python-basic',
    name: 'Basic Python',
    language: 'python',
    packages: [],
    code: `# Write your Python code here
import os

database_url = os.getenv('DATABASE_URL', 'sqlite:///default.db')
print(f"Database URL: {database_url}")

debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
print(f"Debug mode: {debug_mode}")

print("Hello, World!")
`,
  },
  {
    key: 'python-requests',
    name: 'HTTP + JSON (requests)',
    language: 'python',
    packages: ['requests'],
    code: `import requests

r = requests.get("https://httpbin.org/json")
data = r.json()
print("status:", r.status_code)
print("slideshow title:", data["slideshow"]["title"])
`,
  },
  {
    key: 'python-gradio',
    name: 'Gradio App',
    language: 'python',
    packages: ['gradio'],
    code: `import gradio as gr

def greet(name):
    return f"Hello, {name}!"

with gr.Blocks() as demo:
    inp = gr.Textbox(label="Your name")
    out = gr.Textbox(label="Greeting")
    btn = gr.Button("Greet")
    btn.click(fn=greet, inputs=inp, outputs=out)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
`,
  },
  {
    key: 'python-fastapi',
    name: 'FastAPI App',
    language: 'python',
    packages: ['fastapi', 'uvicorn'],
    code: `from fastapi import FastAPI
import uvicorn

app = FastAPI(title="My API", description="A simple FastAPI application")

@app.get("/")
def read_root():
    return {"message": "Hello World", "status": "running"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
`,
  },
  {
    key: 'python-flask',
    name: 'Flask App',
    language: 'python',
    packages: ['flask'],
    code: `from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>My Flask App</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: #333; }
        .btn { background: #007bff; color: white; padding: 10px 20px;
               text-decoration: none; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Welcome to My Flask App!</h1>
        <p>This is a simple Flask application.</p>
        <a href="/api/data" class="btn">View API Data</a>
    </div>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    return jsonify({
        "message": "Hello from Flask!",
        "data": [1, 2, 3, 4, 5],
        "status": "success"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
`,
  },
  {
    key: 'python-dash',
    name: 'Dash App',
    language: 'python',
    packages: ['dash', 'plotly', 'pandas', 'numpy'],
    code: `import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd

df = pd.DataFrame({
    'Fruit': ['Apples', 'Oranges', 'Bananas', 'Grapes'],
    'Amount': [4, 1, 2, 3],
    'City': ['SF', 'SF', 'NYC', 'NYC']
})

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("My Dash Application", style={'textAlign': 'center'}),
    html.Div([
        html.Label("Select City:"),
        dcc.Dropdown(
            id='city-dropdown',
            options=[{'label': city, 'value': city} for city in df['City'].unique()],
            value='SF'
        )
    ], style={'width': '48%', 'display': 'inline-block'}),
    dcc.Graph(id='fruit-graph'),
])

@app.callback(
    Output('fruit-graph', 'figure'),
    Input('city-dropdown', 'value')
)
def update_graph(selected_city):
    filtered_df = df[df['City'] == selected_city]
    return px.bar(filtered_df, x='Fruit', y='Amount',
                  title=f'Fruit Amount in {selected_city}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True)
`,
  },

  // ---------- Node.js ----------
  {
    key: 'node-basic',
    name: 'Basic Node.js',
    language: 'node',
    packages: [],
    code: `// Basic Node.js
const greet = (name) => \`Hello, \${name}!\`;

console.log(greet("World"));
console.log("node version:", process.version);
console.log("NODE_ENV:", process.env.NODE_ENV || "(not set)");
`,
  },
  {
    key: 'node-fetch',
    name: 'HTTP + JSON (fetch)',
    language: 'node',
    packages: [],
    code: `// Node 18+ ships a global fetch — no packages needed.
(async () => {
  const r = await fetch("https://httpbin.org/json");
  const data = await r.json();
  console.log("status:", r.status);
  console.log("slideshow title:", data.slideshow.title);
})();
`,
  },
  {
    key: 'node-lodash',
    name: 'npm package (lodash)',
    language: 'node',
    packages: ['lodash'],
    code: `const _ = require("lodash");

const people = [
  { name: "ada", team: "a" },
  { name: "grace", team: "a" },
  { name: "linus", team: "b" },
];

console.log(_.groupBy(people, "team"));
console.log("lodash version:", _.VERSION);
`,
  },

  // ---------- Ruby ----------
  {
    key: 'ruby-basic',
    name: 'Basic Ruby',
    language: 'ruby',
    packages: [],
    code: `# Basic Ruby
greet = ->(name) { "Hello, #{name}!" }
puts greet.call("World")
puts "ruby version: #{RUBY_VERSION}"
puts "rails? #{defined?(Rails) ? 'yes' : 'no'}"
`,
  },
  {
    key: 'ruby-json',
    name: 'JSON manipulation',
    language: 'ruby',
    packages: [],
    code: `require "json"

people = [
  { name: "ada", team: "a" },
  { name: "grace", team: "a" },
  { name: "linus", team: "b" },
]

by_team = people.group_by { |p| p[:team] }
puts JSON.pretty_generate(by_team)
`,
  },
  {
    key: 'ruby-colorize',
    name: 'gem (colorize)',
    language: 'ruby',
    packages: ['colorize'],
    code: `require "colorize"

puts "green works".colorize(:green)
puts "red on yellow".colorize(color: :red, background: :yellow)
`,
  },

  // ---------- Bash ----------
  {
    key: 'bash-basic',
    name: 'Basic Bash',
    language: 'bash',
    packages: [],
    code: `#!/usr/bin/env bash
set -euo pipefail

echo "bash version: $BASH_VERSION"
echo "whoami: $(whoami)"
echo "uname: $(uname -a)"
echo "pwd: $(pwd)"
`,
  },
  {
    key: 'bash-files',
    name: 'File operations',
    language: 'bash',
    packages: [],
    code: `#!/usr/bin/env bash
set -euo pipefail

# /tmp is a 128M tmpfs — clean scratch per execution.
echo "hello" > /tmp/note.txt
echo "world" >> /tmp/note.txt
echo "--- files in /tmp ---"
ls -lah /tmp
echo "--- contents ---"
cat /tmp/note.txt
`,
  },
  {
    key: 'bash-jq',
    name: 'jq over stdin',
    language: 'bash',
    packages: [],
    code: `#!/usr/bin/env bash
set -euo pipefail

# curl + jq are preinstalled in the bash runtime.
cat <<'EOF' | jq '.users | map(.name)'
{
  "users": [
    {"name": "ada",   "team": "a"},
    {"name": "grace", "team": "a"},
    {"name": "linus", "team": "b"}
  ]
}
EOF
`,
  },

  // ---------- Go ----------
  {
    key: 'go-basic',
    name: 'Basic Go',
    language: 'go',
    packages: [],
    code: `package main

import (
	"fmt"
	"runtime"
)

func main() {
	fmt.Println("Hello, World!")
	fmt.Println("go version:", runtime.Version())
	fmt.Println("numCPU:", runtime.NumCPU())
}
`,
  },
  {
    key: 'go-json',
    name: 'JSON (encoding/json)',
    language: 'go',
    packages: [],
    code: `package main

import (
	"encoding/json"
	"fmt"
)

type Person struct {
	Name string \`json:"name"\`
	Team string \`json:"team"\`
}

func main() {
	people := []Person{
		{Name: "ada", Team: "a"},
		{Name: "grace", Team: "a"},
		{Name: "linus", Team: "b"},
	}

	byTeam := map[string][]Person{}
	for _, p := range people {
		byTeam[p.Team] = append(byTeam[p.Team], p)
	}

	out, _ := json.MarshalIndent(byTeam, "", "  ")
	fmt.Println(string(out))
}
`,
  },
  {
    key: 'go-http',
    name: 'HTTP client (net/http)',
    language: 'go',
    packages: [],
    code: `package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

func main() {
	resp, err := http.Get("https://httpbin.org/json")
	if err != nil {
		fmt.Println("error:", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var data map[string]any
	_ = json.Unmarshal(body, &data)

	fmt.Println("status:", resp.Status)
	if slideshow, ok := data["slideshow"].(map[string]any); ok {
		fmt.Println("slideshow title:", slideshow["title"])
	}
}
`,
  },
];

export const templatesForLanguage = (language: string): AppTemplate[] =>
  APP_TEMPLATES.filter((t) => t.language === language);

export const defaultTemplateForLanguage = (language: string): AppTemplate | undefined =>
  APP_TEMPLATES.find((t) => t.language === language);

export const templateByKey = (key: string): AppTemplate | undefined =>
  APP_TEMPLATES.find((t) => t.key === key);
