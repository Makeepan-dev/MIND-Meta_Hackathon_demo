
from datetime import datetime
from modules.trusted_sources import TRUSTED_DOMAINS

class MetaLogEntry:
    def __init__(self, task, persona, input_text):
        self.task = task
        self.persona = persona           # Brain handling the query
        self.input_text = input_text
        self.steps = []                  # List of reasoning steps
        self.overall_confidence = 0.0
        self.sources = []                # Sources used
        self.timestamp = datetime.now()
        self.notes = []                  # Optional reasoning notes

    def add_step(self, description, confidence, sources=None):
        if sources is None: 
            sources = []
        self.steps.append({
            "description": description,
            "confidence": float(confidence),
            "sources": sources
        })
        for src in sources:
            if src not in self.sources:
                self.sources.append(src)

    def compute_overall_confidence(self):
        """
        Weighted average of step confidences.
        Weights are determined by Trusted Domains.
        - Trusted Domain: Weight 1.2 (Boost)
        - Normal Source: Weight 1.0
        - No Source: Weight 0.8 (Penalty)
        """
        if not self.steps:
            return 0.0
            
        total_weight = 0
        weighted_sum = 0
        
        # Flatten trusted domains for easy lookup
        all_trusted = [s for cat in TRUSTED_DOMAINS.values() for s in cat]
        
        for step in self.steps:
            step_conf = step['confidence']
            step_sources = step['sources']
            
            # Determine weight based on source quality
            weight = 0.8 # Default penalty for unsourced claims
            
            if step_sources:
                weight = 1.0 # Baseline for sourced claims
                # Check for high-quality trusted sources
                for src in step_sources:
                    if any(t in src for t in all_trusted):
                        weight = 1.2 # Boost for trusted sources
                        break
            
            weighted_sum += step_conf * weight
            total_weight += weight
            
        if total_weight == 0:
            self.overall_confidence = 0.0
        else:
            self.overall_confidence = min(weighted_sum / total_weight, 1.0) # Cap at 1.0
            
        return self.overall_confidence

    def to_dict(self):
        return {
            "task": self.task,
            "persona": self.persona,
            "timestamp": self.timestamp.isoformat(),
            "overall_confidence": f"{self.overall_confidence:.2f}",
            "steps": self.steps,
            "final_response": getattr(self, 'final_response', None)
        }
