---
description: This file describes how to decorate README.md files in the project.
paths: 
  - "**/README.md"
---

# README.md Guidelines

- The README.md file should provide a clear and concise overview of the project
- It should include sections such as:
  - Project Title
  - One-line description
  - (Optional for long-term projects) News (key updates and milestones)
  - Overview (brief project description and key capabilities)
  - (Optional for long-term projects) Architecture (high-level system diagram or description)
  - Quick Start (prerequisites, installation, usage)
  - Results (benchmark results, tables, or figures)
  - Citation (bibtex block)
  - License
  - Acknowledgments

# Protocol for Writing README.md

- Use markdown syntax to format the README.md file
- Use clear and concise language to describe the project and its components
- Include relevant links to documentation, code, and other resources
- Update the `README.md` file when committing changes that affect any of the sections mentioned above

# Decoration

- For long-term projects, consider several decorations on the README.md

## Badges

- Use HTML to create some badges on the top of the README.md

```html
  <!-- Badges -->
  <p align="center">
    <a href="https://github.com/{project}/stargazers">
      <img src="https://img.shields.io/github/stars/{project}?style=for-the-badge&color=yellow" alt="Stars">
    </a>
    <a href="https://github.com/{project}">
      <img src="https://img.shields.io/github/forks/{project}?style=for-the-badge&color=blue" alt="Forks">
    </a>
    <a href="https://opensource.org/licenses/MIT">
      <img src="https://img.shields.io/badge/LICENSE-MIT-green" alt="License: MIT">
    </a>
    <a href="https://www.arxiv.org/">
      <img src="https://img.shields.io/badge/Paper-arXiv-red?style=for-the-badge&logo=arxiv&logoColor=white" alt="arXiv Paper">
    </a>
    <a href="https://github.com/{project}/graphs/contributors">
      <img src="https://img.shields.io/github/contributors/{project}?style=for-the-badge&color=orange" alt="Contributors">
    </a>
  </p>
```

## Star History

```
## 🌟 Star History
[![Star History Chart](https://api.star-history.com/svg?repos={project}&type=Date)](https://www.star-history.com/#{project}&Date)
```

# CI/CD

- For long-term projects, build a CI/CD pipeline to check the code quality and correctness