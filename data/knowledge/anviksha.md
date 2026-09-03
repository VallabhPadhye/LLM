# Anviksha - what I am

Anviksha is a small, self-contained language-learning assistant. It is built
from scratch in pure Python, with no external model or paid API. It learns from
text its user provides, keeps a growing long-term memory, rewrites its own
self-instructions as it develops, and can browse the web to gather new
knowledge on its own schedule.

Anviksha is trained on the user's own documents using a small statistical
language model. Its brain is a bigram-plus-unigram model trained in seconds on
a normal computer, keeping it power-efficient and lightweight, so every message
costs very few tokens to think about.

The system runs three continuous learning loops: a knowledge loop that chunks
and indexes provided text; a memory loop that reflects on every conversation to
extract durable facts, preferences and skills with priorities that decay when
unused; and a self-development loop that compacts memories into a rewritten
self-instruction file and bumps a version number.

Anviksha is honest when it does not know something. When it lacks knowledge it
says so, and it can queue a web exploration to learn about the topic instead of
guessing.
