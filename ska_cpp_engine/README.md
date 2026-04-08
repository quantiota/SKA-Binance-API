# SKA C++ Engine

This folder contains the early development of the native C/C++ version of the SKA Engine.

The objective is to progressively move from a QuestDB-centered workflow to a native low-latency engine capable of processing raw tick data directly, computing entropy and structural probabilities in real time, and supporting regime transitions and trading logic without relying on an external database as the core runtime layer.

QuestDB was useful for prototyping, querying, and visualizing the structure of the market. The transition to C/C++ is the next step toward a faster and more controlled engine architecture built for real-time execution.

## Purpose

The purpose of this development folder is to build the native core of the SKA Engine in C/C++ for real-time market applications.

This work focuses on:

* direct processing of raw tick data
* real-time entropy computation
* structural probability computation
* regime classification
* transition detection
* integration with the LONG/SHORT trading logic

## Why move beyond QuestDB

QuestDB has been very useful for:

* fast experimentation
* SQL-based analysis
* transition studies
* probability visualization
* Grafana dashboards

However, for a real-time SKA Engine, the database-centered architecture becomes limiting when the goal is:

* lower latency
* direct stream processing
* fine memory control
* native execution speed
* tighter integration between signal generation and trading logic

The C/C++ implementation is intended to move the SKA Engine from an analysis-oriented environment to an execution-oriented engine.

## Development direction

The native engine is expected to evolve step by step:

1. ingest raw tick data directly
2. compute entropy online
3. compute structural probability in real time
4. classify structural regimes
5. detect regime transitions
6. support trading bot logic directly from the engine output

The goal is not simply to rewrite the old workflow in another language, but to reorganize the SKA Engine around a true real-time native core.

## Scope

This folder is intended for the development of:

* C/C++ entropy routines
* probability and transition modules
* stream-processing utilities
* engine state management
* experimental native trading logic interfaces
* performance-oriented prototypes

## Status

Early development.

The architecture is still under construction, and the current focus is on building the foundations of the native engine before expanding toward a full production pipeline.

