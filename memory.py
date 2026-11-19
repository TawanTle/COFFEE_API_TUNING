"""What the agent remembers between rounds, saved as JSON so a restart does not forget."""
import json
from collections import defaultdict
from pathlib import Path


class Memory:
    def __init__(self, path: str):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.sent: dict = data.get("sent", {})         # round_id -> offers we sent (with markup and buyer type)
        self.rounds: list = data.get("rounds", [])     # results of cleared rounds, oldest first

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"sent": self.sent, "rounds": self.rounds}, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    """def record_sent(self, round_id: str, offers: list[dict], state: dict, tv: dict) -> None:
        types = {r["rfq_id"]: r["buyer_type"] for r in state["rfqs"]}
        self.sent[round_id] = [{**o, "buyer_type": types[o["rfq_id"]],
                                "markup": round(o["price_per_kg"] / tv[o["lot_id"]], 3)} for o in offers]
        self.save()"""

    def record_results(self, results: dict | None) -> None:
        if not results or not results.get("round_id") or any(r["round_id"] == results["round_id"] for r in self.rounds):
            return
        self.rounds.append(results)
        self.save()

    """def summary(self, last: int = 3) -> str:
        ""A few short lines for the LLM prompt.""
        # TODO: this only looks at the last few rounds. Trends over the whole game, per buyer persona,
        #       may tell you more (ผู้ซื้อแต่ละรายมีนิสัยต่างกัน)
        lines = []
        for rnd in self.rounds[-last:]:
            sent = {(o["rfq_id"], o["lot_id"]): o for o in self.sent.get(rnd["round_id"], [])}
            mine = []
            for o in rnd["my_offers"]:
                s = sent.get((o["rfq_id"], o["lot_id"]), {})
                mine.append(f"{s.get('buyer_type', '?')} x{s.get('markup', '?')} {o['status']}")
            by_type = defaultdict(lambda: [0, 0])
            for row in rnd["market_summary"]:
                by_type[row["buyer_type"]][0] += row["wanted_kg"]
                by_type[row["buyer_type"]][1] += row["bought_kg"]
            market = ", ".join(f"{t} bought {b * 100 // max(w, 1)}% of wanted" for t, (w, b) in by_type.items())
            lines.append(f"{rnd['round_id']}: my offers [{'; '.join(mine) or 'none'}]; market: {market}")
        return "\n".join(lines) or "none yet" 
    """
    
    def record_sent(self, round_id: str, offers: list[dict], state: dict, tv: dict) -> None:
        rfqs = {r["rfq_id"]: r for r in state["rfqs"]}
        self.sent[round_id] = []

        for offer in offers:
            rfq = rfqs.get(offer["rfq_id"], {})
            lot_id = offer["lot_id"]

            self.sent[round_id].append({
                **offer,
                "buyer_type": rfq.get("buyer_type", "UNKNOWN"),
                "buyer": rfq.get("buyer", rfq.get("buyer_type", "UNKNOWN")),
                "markup": round(offer["price_per_kg"] / tv[lot_id], 3),
            })

        self.save()

    def summary(self, last: int = 3) -> str:
        """สรุปผลทั้งเกมแยกตามผู้ซื้อ พร้อมรายละเอียดรอบล่าสุด."""
        def new_stats():
            return {
                "offered_kg": 0,
                "filled_kg": 0,
                "markup_weighted": 0.0,
                "statuses": defaultdict(int),
            }

        totals = defaultdict(new_stats)
        by_round = []

        for rnd in self.rounds:
            sent = {
                (o["rfq_id"], o["lot_id"]): o
                for o in self.sent.get(rnd["round_id"], [])
            }
            round_stats = defaultdict(new_stats)

            for result in rnd.get("my_offers", []):
                offer = sent.get((result["rfq_id"], result["lot_id"]), {})
                buyer_type = offer.get("buyer_type", "UNKNOWN")
                buyer = offer.get("buyer", buyer_type)
                key = (buyer_type, buyer)

                offered_kg = int(result.get("kg", 0) or 0)
                filled_kg = int(result.get("filled_kg", 0) or 0)
                markup = float(offer.get("markup", 0) or 0)
                status = result.get("status", "UNKNOWN")

                for stats in (totals[key], round_stats[key]):
                    stats["offered_kg"] += offered_kg
                    stats["filled_kg"] += filled_kg
                    stats["markup_weighted"] += markup * offered_kg
                    stats["statuses"][status] += 1

            by_round.append((rnd.get("round_id", "?"), round_stats))

        if not totals:
            return "no results yet"

        lines = ["Whole-game results by buyer:"]
        for (buyer_type, buyer), stats in sorted(totals.items()):
            avg_markup = (
                stats["markup_weighted"] / stats["offered_kg"]
                if stats["offered_kg"] else 0
            )
            statuses = ", ".join(
                f"{name}={count}"
                for name, count in sorted(stats["statuses"].items())
            )
            lines.append(
                f"{buyer_type}/{buyer}: markup≈{avg_markup:.2f}, "
                f"sold={stats['filled_kg']}/{stats['offered_kg']}kg; {statuses}"
            )

        lines.append(f"Last {last} rounds:")
        for round_id, stats_by_buyer in by_round[-last:]:
            details = []
            for (buyer_type, buyer), stats in sorted(stats_by_buyer.items()):
                avg_markup = (
                    stats["markup_weighted"] / stats["offered_kg"]
                    if stats["offered_kg"] else 0
                )
                statuses = ", ".join(
                    f"{name}={count}"
                    for name, count in sorted(stats["statuses"].items())
                )
                details.append(
                    f"{buyer_type}/{buyer} x{avg_markup:.2f}: "
                    f"{stats['filled_kg']}/{stats['offered_kg']}kg ({statuses})"
                )

            lines.append(f"{round_id}: {'; '.join(details) or 'no offers'}")

        return "\n".join(lines)