from setuptools import setup, find_packages

setup(
    name="spacetraders-zero",
    version="0.1.0",  # Simple version string
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,  # Include files from MANIFEST.in
    install_requires=[
        "requests>=2.31.0",
        "pydantic>=2.5.2",
        "python-dotenv>=1.0.0",
        "responses>=0.24.1",
        "aiohttp>=3.9.1",
    ],
    python_requires=">=3.12",
)
