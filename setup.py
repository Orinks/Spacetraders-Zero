from setuptools import setup, find_packages

setup(
    name="spacetraders-zero",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "pydantic>=2.5.2",
        "python-dotenv>=1.0.0",
        "responses>=0.24.1",
    ],
    python_requires=">=3.12",
)
