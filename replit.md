# Overview

This is a hockey league management system (BISHL) built with FastAPI and MongoDB. The system manages tournaments, teams, players, matches, referees, and various administrative functions for a hockey league. It includes features for match scheduling, score tracking, referee assignments, player management, and document handling.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Framework
- **FastAPI**: Modern Python web framework providing automatic API documentation and type validation
- **Motor**: Asynchronous MongoDB driver for Python, enabling non-blocking database operations
- **Pydantic**: Data validation and serialization using Python type annotations

## Database Design
- **MongoDB**: Document-based NoSQL database storing hierarchical tournament structures
- **Collections**: tournaments, matches, players, clubs, users, venues, assignments, messages, posts, documents
- **Embedded Documents**: Teams within clubs, seasons within tournaments, rounds within seasons, matchdays within rounds

## Authentication & Authorization
- **JWT Tokens**: Stateless authentication using JSON Web Tokens with configurable expiration
- **Role-based Access**: Multiple user roles (ADMIN, REFEREE, CLUB_ADMIN, etc.) with different permissions
- **bcrypt**: Password hashing for secure credential storage

## API Architecture
- **Router-based Structure**: Modular endpoint organization by resource type (clubs, tournaments, matches, etc.)
- **CORS Middleware**: Cross-origin resource sharing enabled for frontend integration
- **Request/Response Models**: Pydantic models for input validation and output serialization

## File Management
- **Cloudinary Integration**: Cloud-based storage for images, documents, and logos
- **Image Processing**: Automatic resizing and optimization for player photos and venue images
- **Document Upload**: Support for PDF, DOCX, XLSX file types

## Email System
- **FastAPI-Mail**: SMTP-based email service for notifications and communications
- **HTML Templates**: Formatted email content for match assignments and notifications

## Data Import/Export
- **CSV Import Scripts**: Bulk data import utilities for players, teams, schedules, and venues
- **ISHD Integration**: External hockey database synchronization for player licensing
- **Batch Processing**: Command-line tools for data migration and updates

## Business Logic
- **Match Management**: Comprehensive scoring, penalties, and roster tracking
- **Referee Assignment**: Automated and manual referee scheduling with availability tracking
- **Statistics Calculation**: Real-time standings, player stats, and team performance metrics
- **Tournament Structure**: Flexible hierarchy supporting multiple seasons, rounds, and matchdays

# External Dependencies

## Cloud Services
- **Cloudinary**: Image and document storage with transformation capabilities
- **MongoDB Atlas**: Cloud-hosted MongoDB database service

## Email Service
- **SMTP Provider**: Configurable email server for automated notifications and communications

## External APIs
- **ISHD Database**: Hockey player licensing and registration data synchronization
- **Genderize.io**: Gender prediction service for player data completion

## Development Tools
- **Motor**: Async MongoDB driver for Python
- **FastAPI-Mail**: Email functionality integration
- **PyJWT**: JSON Web Token implementation
- **Passlib**: Password hashing utilities
- **Certifi**: SSL certificate validation for secure connections