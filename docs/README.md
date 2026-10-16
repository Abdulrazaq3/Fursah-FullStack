![SAAI — Learn AI by building](assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Design and decisions

**Previous:** [Main guide](../README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Data](../data/README.md)

This is the map of what we decided, why we chose it and what has been verified. The underlying design notes and measured reviews are currently written in Arabic.

## Start with the build notes

The [build notes](../fursah-ai-build-notes.md) follow eight stages from understanding the problem to building and evaluating the system. We are in **stage 8**: a small retrieval experiment is complete, and application integration remains ahead.

## Design references

| Read | Question it answers |
|---|---|
| [Project structure](project-structure.md) | Where do the frontend, API, data and experiments belong? |
| [Data model](data-model.md) | How are announcements, opportunities, facts and evidence linked? |
| [Tool design](agent-tools.md) | What are search, details and verification responsible for? |
| [RAG design](rag-design.md) | What is embedded, what is filtered and how do we reach the evidence? |
| [First retrieval experiment](first-retrieval-experiment.md) | Why try BGE-M3, pgvector and exact cosine search? |

## Evidence from execution

| Evidence | Scope |
|---|---|
| [Retrieval review](../results/retrieval-review.md) | Four opportunities, eight development queries and measured timings |
| [Numeric retrieval report](../results/retrieval-report.json) | Configuration, versions, hashes, rankings and scores |
| [Fullstack verification](fullstack-verification.md) | Browser-to-API transport and the expected unfinished response |
| [Upstream import record](upstream-import.json) | GitHub revision and the raw-data checksum |

## Keeping the record useful

For each meaningful change, add the date, decision, reason, measured evidence and remaining work to the build notes. Distinguish a proposed design from an implemented component or a measured result.

The shared README banner lives at `assets/saai-header.png`. Each guide references this one local asset so it travels with the repository.

**Next: [understand the source data](../data/README.md).**
