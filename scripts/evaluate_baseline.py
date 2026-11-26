"""Synthetic illustrative rule baseline, NOT held-out agent evaluation.

For apples-to-apples future comparison, freeze an independent dataset and label it
blind to predictions. No outcome from this script should be presented as client KPI.
"""
from collections import Counter
import json
from app.services import classify

CASES = [
    # Deliberate edge cases: some should be missed by the simple rule system.
    ("Can I exchange medium leggings for size L?", "exchanges"),
    ("The sports bra fits too tight, need a different size", "exchanges"),
    ("Do you have the same shorts in extra large?", "exchanges"),
    ("I would like to swap my leggings for another size", "exchanges"),
    ("Please replace my M tee with L", "exchanges"),
    ("The carrier says my package is missing", "missing_package"),
    ("Tracking shows delivery exception", "missing_package"),
    ("My sportswear order never arrived", "missing_package"),
    ("It says delivered but I cannot find the box", "missing_package"),
    ("The parcel was lost in transit", "missing_package"),
    ("Please refund the running shorts", "refunds"),
    ("I want my money back for order 1002", "refunds"),
    ("The payment charged twice", "refunds"),
    ("My card was billed incorrectly, help", "refunds"),
    ("Can you reimburse the shipping fee?", "refunds"),
    ("Can I return unused workout leggings?", "returns"),
    ("I'd like to send the shirt back", "returns"),
    ("I wore these socks, can I return them?", "returns"),
    ("How do I start a return?", "returns"),
    ("The shorts are damaged, I want to send them back", "returns"),
    ("Track my package please", "order_tracking"),
    ("What is the tracking number for my order?", "order_tracking"),
    ("Where is my order 1001?", "order_tracking"),
    ("Can you check the latest carrier scan?", "order_tracking"),
    ("What's my delivery status?", "order_tracking"),
    ("What is the standard shipping cost in the US?", "shipping"),
    ("Do you ship to Hawaii?", "shipping"),
    ("How long will delivery take?", "shipping"),
    ("Is free delivery offered over $75?", "shipping"),
    ("What's the shipping fee?", "shipping"),
    ("Please explain your returns policy", "policy_question"),
    ("What's your warranty policy for sportswear?", "policy_question"),
    ("What conditions make an item final sale?", "policy_question"),
    ("Do I need original tags for an exchange under your policy?", "policy_question"),
    ("Can you send me the terms and conditions?", "policy_question"),
    ("Please change the email on my account", "other"),
    ("I forgot my password", "other"),
    ("Thank you for resolving my issue", "other"),
    ("Do you sell yoga mats?", "other"),
    ("I have a wholesale partnership inquiry", "other"),
]


def metrics():
    labels = sorted({gold for _, gold in CASES} | {classify(text) for text, _ in CASES})
    records = [(text, gold, classify(text)) for text, gold in CASES]
    per_class = {}
    for cls in labels:
        tp = sum(g == cls and p == cls for _, g, p in records)
        fp = sum(g != cls and p == cls for _, g, p in records)
        fn = sum(g == cls and p != cls for _, g, p in records)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        per_class[cls] = {"support": Counter(g for _, g, _ in records)[cls],
                          "precision": round(precision, 4), "recall": round(recall, 4),
                          "f1": round(2*precision*recall/(precision+recall), 4) if precision+recall else 0}
    return {"dataset": "v0.1 hand-authored sportswear examples; illustrative, NOT held-out",
            "samples": len(records), "accuracy": round(sum(g == p for _,g,p in records)/len(records), 4),
            "macro_f1": round(sum(v["f1"] for v in per_class.values())/len(per_class), 4),
            "per_class": per_class,
            "errors": [{"text":t,"expected":g,"predicted":p} for t,g,p in records if g!=p]}

if __name__ == "__main__":
    print(json.dumps(metrics(), indent=2))
