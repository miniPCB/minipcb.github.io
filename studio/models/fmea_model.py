from .table_base import SimpleTableModel

FMEA_HEADERS = [
    "Item","Potential Failure Mode","Potential Effect of Failure","Severity",
    "Potential Causes/Mechanisms","Occurrence","Current Process Controls","Detection",
    "RPN","Recommended Actions","Responsibility","Target Completion Date",
    "Actions Taken","Resulting Severity","Resulting Occurrence","Resulting Detection","New RPN"
]

class FMEAModel(SimpleTableModel):
    def __init__(self, rows=None, parent=None):
        super().__init__(FMEA_HEADERS, rows, parent)
