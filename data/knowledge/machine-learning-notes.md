# Machine learning notes

Machine learning is a way to give computers the ability to learn patterns from
data without being explicitly programmed for every rule. The main types are
supervised learning, where the model is trained on labelled examples;
unsupervised learning, where the model finds structure in unlabelled data; and
reinforcement learning, where an agent learns by taking actions and receiving
rewards or penalties.

A model generalizes when it performs well not just on the data it was trained
on but also on new, unseen data. Overfitting happens when a model memorizes the
training data too closely and fails on new examples. Underfitting happens when
a model is too simple to capture the real pattern.

Features are the individual measurable properties of the data used as inputs.
Labels are the answers we want the model to predict. Training means adjusting
the model's parameters to reduce the difference between its predictions and the
true labels; that difference is measured by a loss function.

An embedding is a way of representing words or items as vectors of numbers so
that similar items end up close together in that vector space. Language models
predict the next word given the previous words, and they can be fine-tuned to
follow instructions or to specialize in a particular domain.

The larger a model, the more data and computing it usually needs. Small models
trade a little quality for speed, low power use, and low cost, which makes them
ideal when you want an assistant that runs on a normal computer and is cheap to
operate.
