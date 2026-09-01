# Frontend Contribution & Future Improvements

## Overview

During the HackBricks Hackathon, I primarily contributed to the frontend development, UI/UX design, and user-facing application features of Astitva.

The frontend was developed as a browser-based prototype focused on helping women navigating major life transitions access relevant support and organize their next steps through a personalized life roadmap.

## Frontend Contribution

My primary contribution was the frontend implementation and user experience of the application.

### Core User Experience

The frontend was designed around the following flow:

**User Context → Life Profile → Support → Personalized Roadmap → Actions → Progress → Roadmap Recalculation**

The interface was structured to help users move from understanding their situation to identifying relevant support and tracking their progress.

### Features Implemented

* User onboarding and context collection
* Dashboard with personalized next actions
* Personalized roadmap and milestone tracking
* Ability to mark roadmap tasks as completed
* Dynamic roadmap recalculation based on progress
* Opportunities/support discovery
* Opportunity detail views
* Progress tracking
* Guided user interaction flow
* Responsive navigation and layouts
* Accessibility-focused UI elements and interaction patterns

## Frontend Architecture

The frontend was organized into reusable components and service layers.

* **React + TypeScript** for the application interface and component development
* **Vite** for development and build tooling
* **Tailwind CSS** for styling and responsive layouts
* Reusable UI primitives and domain-specific Astitva components
* Centralized mock data for the prototype
* Service layer for application data access
* Separate roadmap engine for decision logic, ranking, progress, unlocking, and recalculation
* Shared TypeScript models for consistent data structures

The prototype was designed with a separation between the UI, data-access layer, and decision logic so that the mock data layer could later be replaced with backend APIs.

## Current Prototype Architecture

The current frontend prototype operates entirely in the browser using local mock data.

The frontend service layer is structured so that future backend integration can replace the mock implementations with HTTP/API calls while preserving the existing application interfaces.

Planned backend interactions include:

* User profile retrieval and updates
* Life-profile creation
* Roadmap retrieval and updates
* Roadmap milestone progress updates
* Opportunities retrieval
* Opportunity details
* Guided messaging

## Future Improvements

The following improvements can be considered as the project moves from prototype to a more complete product:

### Backend Integration

* Connect the frontend to the FastAPI backend and PostgreSQL services.
* Replace mock data with authenticated API requests.
* Implement persistent user sessions and real authentication.

### User Experience

* Improve loading, empty, and error states.
* Add stronger form validation and user feedback.
* Improve responsive behaviour across different screen sizes.
* Increase component reusability across application flows.

### Accessibility

* Continue improving keyboard navigation and screen-reader support.
* Maintain visible focus states and accessible controls.
* Expand accessibility testing across major user workflows.

### Product Features

* Integrate verified support and government-scheme information.
* Connect roadmap generation to backend decision and recommendation services.
* Add real-time progress persistence.
* Integrate future case-worker and mentor workflows.
* Provide clearer explanations for recommendations and roadmap changes.

## Contribution Summary

My primary role in Astitva was focused on **frontend development, UI/UX design, and implementation of user-facing application features** during the hackathon.

This frontend prototype provides the user-facing foundation that can be integrated with the project's backend, retrieval, recommendation, and future orchestration components.
