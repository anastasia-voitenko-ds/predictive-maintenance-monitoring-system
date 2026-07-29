# PC Predictive Maintenance & Telemetry Monitoring System

A full-stack monitoring system that collects real-time PC telemetry, stores historical system metrics, and predicts potential hardware failures using machine learning.

---

## Overview

This project was developed as part of a university coursework to demonstrate the design and implementation of a complete predictive monitoring system.

The application continuously collects hardware telemetry, processes incoming data through a FastAPI backend, stores records in MongoDB, and applies a machine learning model to classify potential hardware failures. The system also provides a web dashboard for monitoring device status and historical metrics.

---

## Features

- Real-time telemetry collection
- Machine learning-based hardware failure prediction
- REST API built with FastAPI
- MongoDB document database
- Interactive monitoring dashboard
- Desktop telemetry collection agent
- Dockerized deployment

---

## Project Structure

```

backend/ FastAPI backend service

desktop-app/ Desktop telemetry collection agent

frontend/ React dashboard

ml/ Machine learning model

docker-compose.yml Docker configuration

```

---

## Technologies

- Python
- FastAPI
- MongoDB
- React
- XGBoost
- Docker

---

## Machine Learning

The project uses an XGBoost classification model trained to identify five hardware health states based on collected telemetry data.

Failure categories include:

- Normal Operation
- Battery Failure
- Overheating
- CPU Failure
- Network Failure

---

## Future Improvements

Possible future enhancements include:

- Cloud deployment
- Real-time notifications
- Advanced analytics dashboard
- Model retraining pipeline

---

## Author

**Anastasia Voitenko**

Data Science Student

Technical University of Moldova
