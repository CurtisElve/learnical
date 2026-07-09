"""Seed the topic library with a starter curriculum.

Run once against a fresh or existing database:

    .venv/bin/python seed_topics.py

Idempotent: topics already present (same subject/grade/name) are skipped.
"""

from sqlmodel import Session, select

from database import engine
from models import SQLModel, Topic

# (subject, grade, unit, name, description, skills)
TOPICS: list[tuple[str, str, str, str, str, list[str]]] = [
    # --- Math ---
    ("math", "1", "Addition & Subtraction", "Adding within 20", "Single-digit sums and sums to 20.", ["addition"]),
    ("math", "1", "Addition & Subtraction", "Subtracting within 20", "Taking away within 20.", ["subtraction"]),
    ("math", "1", "Place Value", "Tens and ones", "Understanding two-digit numbers as tens and ones.", ["place_value"]),
    ("math", "2", "Addition & Subtraction", "Two-digit addition with regrouping", "Carrying across the tens place.", ["addition", "regrouping"]),
    ("math", "2", "Addition & Subtraction", "Two-digit subtraction with regrouping", "Borrowing across the tens place.", ["subtraction", "regrouping"]),
    ("math", "2", "Measurement", "Telling time", "Reading clocks to five minutes.", ["time"]),
    ("math", "2", "Money", "Counting coins and bills", "Making amounts with coins and bills.", ["money"]),
    ("math", "3", "Multiplication & Division", "Multiplication facts to 10x10", "Times tables fluency.", ["multiplication"]),
    ("math", "3", "Multiplication & Division", "Division facts", "Dividing using known multiplication facts.", ["division"]),
    ("math", "3", "Fractions", "Fractions on a number line", "Unit fractions and placing fractions on a line.", ["fractions"]),
    ("math", "3", "Geometry", "Perimeter", "Perimeter of rectangles and polygons.", ["perimeter", "geometry"]),
    ("math", "4", "Multiplication & Division", "Multi-digit multiplication", "Multiplying 2-3 digit numbers.", ["multiplication"]),
    ("math", "4", "Multiplication & Division", "Long division", "Dividing multi-digit numbers with remainders.", ["division", "long_division"]),
    ("math", "4", "Fractions", "Equivalent fractions", "Finding and recognizing equivalent fractions.", ["fractions", "equivalent_fractions"]),
    ("math", "4", "Fractions", "Comparing fractions", "Comparing with common denominators and benchmarks.", ["fractions", "comparing"]),
    ("math", "4", "Geometry", "Area of rectangles", "Area as length times width.", ["area", "geometry"]),
    ("math", "5", "Fractions", "Adding fractions with unlike denominators", "Finding common denominators to add.", ["fractions", "addition"]),
    ("math", "5", "Fractions", "Multiplying fractions", "Fraction times fraction and fraction of a whole.", ["fractions", "multiplication"]),
    ("math", "5", "Decimals", "Decimal operations", "Adding, subtracting, and multiplying decimals.", ["decimals"]),
    ("math", "5", "Geometry", "Volume of rectangular prisms", "Volume as area of base times height.", ["volume", "geometry"]),
    ("math", "6", "Ratios & Proportions", "Ratios and rates", "Writing and simplifying ratios; unit rates.", ["ratios", "rates"]),
    ("math", "6", "Ratios & Proportions", "Percent problems", "Percent of a number; finding the whole.", ["percent"]),
    ("math", "6", "Expressions", "Evaluating expressions", "Order of operations with variables.", ["expressions", "order_of_operations"]),
    ("math", "6", "Negative Numbers", "Integers on the number line", "Ordering, absolute value, and adding integers.", ["integers"]),
    ("math", "7", "Equations", "One-step and two-step equations", "Solving linear equations with one variable.", ["equations", "algebra"]),
    ("math", "7", "Proportional Relationships", "Proportional reasoning", "Constant of proportionality; scaling.", ["proportions"]),
    ("math", "7", "Geometry", "Circles: circumference and area", "Working with pi.", ["circles", "geometry"]),
    ("math", "8", "Linear Equations", "Slope and y-intercept", "Slope from points and graphs; y = mx + b.", ["slope", "linear_equations"]),
    ("math", "8", "Linear Equations", "Systems of equations", "Solving by substitution and elimination.", ["systems_of_equations", "algebra"]),
    ("math", "8", "Geometry", "Pythagorean theorem", "Finding missing side lengths in right triangles.", ["pythagorean_theorem", "geometry"]),
    ("math", "8", "Exponents", "Exponent rules", "Product, quotient, and power rules; negative exponents.", ["exponents"]),
    # --- Science ---
    ("science", "4", "Energy", "Forms of energy", "Kinetic, potential, thermal, and electrical energy.", ["energy"]),
    ("science", "5", "Matter", "States of matter", "Solids, liquids, gases, and changes of state.", ["matter", "states_of_matter"]),
    ("science", "6", "Earth Science", "The water cycle", "Evaporation, condensation, precipitation.", ["water_cycle"]),
    ("science", "7", "Life Science", "Cells and organelles", "Cell structure and the jobs of organelles.", ["cells"]),
    ("science", "8", "Physics", "Forces and motion", "Newton's laws, speed, and acceleration.", ["forces", "motion"]),
    # --- English (academics: grammar & comprehension) ---
    ("english", "3", "Grammar", "Parts of speech", "Nouns, verbs, adjectives, and adverbs.", ["parts_of_speech", "grammar"]),
    ("english", "5", "Grammar", "Punctuation and capitalization", "Commas, quotation marks, and capital letters.", ["punctuation", "grammar"]),
    ("english", "7", "Writing", "Main idea and supporting details", "Identifying the main idea of a passage.", ["reading_comprehension"]),
]


def seed() -> None:
    SQLModel.metadata.create_all(engine)
    added = 0
    with Session(engine) as session:
        for subject, grade, unit, name, description, skills in TOPICS:
            exists = session.exec(
                select(Topic).where(
                    Topic.subject == subject, Topic.grade == grade, Topic.name == name
                )
            ).first()
            if exists:
                continue
            session.add(
                Topic(
                    subject=subject,
                    grade=grade,
                    unit=unit,
                    name=name,
                    description=description,
                    skills=skills,
                )
            )
            added += 1
        session.commit()
    print(f"Seeded {added} topics ({len(TOPICS)} defined).")


if __name__ == "__main__":
    seed()
