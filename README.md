<div align="center">
  <img src="assets/ii.png" width="200"/>

# II Agent

[![GitHub stars](https://img.shields.io/github/stars/Intelligent-Internet/ii-agent?style=social)](https://github.com/Intelligent-Internet/ii-agent/stargazers)
[![Discord Follow](https://dcbadge.limes.pink/api/server/yDWPsshPHB?style=flat)](https://discord.gg/yDWPsshPHB)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Blog](https://img.shields.io/badge/Blog-II--Agent-blue)](https://ii.inc/web/blog/post/ii-agent)
[![GAIA Benchmark](https://img.shields.io/badge/GAIA-Benchmark-green)](https://ii-agent-gaia.ii.inc/)
[<img src="https://devin.ai/assets/deepwiki-badge.png" alt="Ask DeepWiki.com" height="20"/>](https://deepwiki.com/Intelligent-Internet/ii-agent)

</div>

II-Agent is an open-source intelligent assistant designed to streamline and enhance workflows across multiple domains. It represents a significant advancement in how we interact with technology—shifting from passive tools to intelligent systems capable of independently executing complex tasks.

II-Agent Chat also feature within II-Agent that lets you work across multiple models and tools in one place. The web-hosted version comes with Gemini 3, Sonnet 4.5, and GPT-5 ready to use out of the box. You can connect your own API keys, switch models within a single thread, and use them alongside Claude Skills, GPT-5 Code Interpreter, and text file search.


### Discord Join US

📢 Join Our [Discord Channel](https://discord.gg/yDWPsshPHB)! Looking forward to seeing you there! 🎉

### Try now on our web application version at [II-Agent](https://agent.ii.inc/)

## Introduction

<https://github.com/user-attachments/assets/2707b106-f37d-41a8-beff-8802b1c9b186>

## Key Features:
* Full-Stack Development: Complete web app scaffolding and iterative development. From initial setup to deployment, II-Agent handles the entire development lifecycle with intelligent code generation and optimization.
* Slide Creation: Transform short briefs into polished presentations. Create professional slides and decks with intelligent content structuring, design suggestions, and automated formatting.
* Deep Research: Comprehensive research capabilities through tight integration with II-Researcher. Conduct thorough investigations, analyze data, and generate detailed reports with our specialized research agent.

## SWE-Bench Pro

<img width="1778" height="1060" alt="swepro" src="https://github.com/user-attachments/assets/e955538d-986a-4c74-96b9-dbeb56e803e1" />



## Installation

For the latest installation and deployment instructions, please refer to our [official guide](https://intelligent-internet.github.io/ii-agent-prod/)

[![Installation Guide](https://img.youtube.com/vi/wPpeJMbdGi4/maxresdefault.jpg)](https://www.youtube.com/watch?v=wPpeJMbdGi4)

## Optional provider integrations

Some integrations (Google APIs, Anthropic, e2b code interpreter, etc.) are heavy and have many transitive dependencies. To keep development and CI installs fast and deterministic, these are provided as an optional extra named `providers`.

To install the providers extra locally (recommended when you need provider integrations), use the `constraints.txt` included in the repository to avoid pip resolver backtracking:

```powershell
python -m pip install -e "[.providers]" -c constraints.txt
```

Or install both dev and providers when you need tests and provider integrations:

```powershell
python -m pip install -e ".[dev]" -c constraints.txt
python -m pip install -e ".[providers]" -c constraints.txt
```

If you prefer not to install providers, the project will still work for most development tasks without them.
