from setuptools import setup


def read_requirements(path="requirements.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def read_readme(path="README.md"):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


setup(
    name="perceptai",
    version="0.2.0",
    description="PerceptAI: universal perception layer for AI agents — screen-driven automation without DOM access.",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Neeraj Patil",
    license="Apache-2.0",
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries",
    ],
    packages=["perceptai"],
    install_requires=read_requirements(),
    python_requires=">=3.10",
)
