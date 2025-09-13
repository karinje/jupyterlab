from setuptools import setup, find_packages
import os

setup(
    name="jupyter-agent-lg",
    version="1.0.0",
    description="LangGraph-based data analysis agent for JupyterLab",
    long_description=open("README.md", "r", encoding="utf-8").read()
    if os.path.exists("README.md")
    else "",
    long_description_content_type="text/markdown",
    author="JupyterLab Contributors",
    author_email="jupyter@googlegroups.com",
    url="https://github.com/jupyterlab/jupyterlab",
    packages=find_packages(),
    package_data={
        "jupyter_agent_lg": ["*.py"],
    },
    install_requires=[
        "langgraph>=0.2.0",
        "langchain>=0.3.0",
        "langchain-openai>=0.2.0",
        "langchain-anthropic>=0.2.0",
        "openai>=1.50.0",
        "anthropic>=0.34.0",
        "pydantic>=2.0.0",
        "aiohttp>=3.9.0",
        "jupyter-server>=2.0.0",
        "tornado>=6.0.0",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Jupyter",
        "Framework :: Jupyter :: JupyterLab",
        "Framework :: Jupyter :: JupyterLab :: 4",
    ],
    keywords="jupyter jupyterlab agent langgraph ai llm",
)
