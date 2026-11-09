---
name: taste
description: Anti-slop constraints for human-viewed web UI work. Use before creating or visually styling a web page, component, or dashboard.
---

# Taste: frontend don'ts

Negative constraints only; user requests and other explicit
styles still win. Stacking the below is what reads as AI-made
on sight.

Use the shared `read_file` and `find_files` operations to inspect
existing styles before changing them. This skill provides
instructions, not authorization or tools.

Do not use: purple/indigo/violet accents or hero gradients;
gradient headline text; cream whole-page backgrounds; aurora
blobs or identical glows on every card; a single font family as
the only identity; gray body text; one font weight and size
throughout; tracked all-caps micro-kickers above every section;
centered hero of pill + headline + two CTAs; identical 3-card
feature grids with boxed icons; 8+ word 48px+ headlines that say
nothing; bento grids for everything; repeated
eyebrow-headline-3cards sections; one radius on every element;
glassmorphism on every surface; hover-lift on cards; emoji as
feature icons; left-border accent cards or nested cards;
fade-up on everything; motion ignoring
`prefers-reduced-motion`; purposeless hand-drawn SVG mascots.

Keep value-identical migrations (token extraction, renames)
free of visual changes: no restyling rides along.
