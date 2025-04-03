# BusyBusy API Documentation

## Overview

This API serves as a middleware between client applications and the BusyBusy GraphQL API. It provides simplified endpoints for retrieving project, budget, employee, cost code, and equipment data with proper formatting and hierarchy handling.

## API Endpoints

### Projects API

**Endpoint:** `GET /api/projects`

**Parameters:**
- `is_archived` (query): Boolean flag to retrieve active or archived projects
- `timezone` (query): Timezone in GMT format (e.g., GMT+05:30)
- `key-authorization` (header): API key for authentication

**Response:**
Returns a hierarchical list of projects with detailed information including:
- Project details (ID, title, number, customer)
- Address information
- GPS requirements
- Project hierarchy (up to 7 levels deep)
- Group information
- Creation and update timestamps

### Budgets API

**Endpoint:** `GET /api/budgets`

**Parameters:**
- `is_archived` (query): Boolean flag to retrieve active or archived budgets
- `key-authorization` (header): API key for authentication

**Response:**
Returns budget data including:
- Project information
- Labor hours and costs
- Progress values and quantities
- Cost code details
- Status information

### Employees API

**Endpoint:** `GET /api/employees`

**Parameters:**
- `is_archived` (query): Boolean flag to retrieve active or archived employees
- `timezone` (query): Timezone in GMT format
- `key-authorization` (header): API key for authentication

**Response:**
Returns employee data including:
- Personal information (name, contact details)
- Wage and payroll information
- Position and group details
- GPS settings
- Creation and update timestamps

### Cost Codes API

**Endpoint:** `GET /api/cost-codes`

**Parameters:**
- `is_archived` (query): Boolean flag to retrieve active or archived cost codes
- `timezone` (query): Timezone in GMT format
- `key-authorization` (header): API key for authentication

**Response:**
Returns cost code data including:
- Cost code ID and title
- Unit information
- Group details
- Creation and update timestamps

### Equipment API

**Endpoint:** `GET /api/equipment`

**Parameters:**
- `is_deleted` (query): Boolean flag to retrieve active or deleted equipment
- `timezone` (query): Timezone in GMT format
- `key-authorization` (header): API key for authentication

**Response:**
Returns equipment data including:
- Equipment details (name, type, category)
- Make and model information
- Running hours
- Cost rates
- Creation and update timestamps

## Data Flow Architecture

### Budget API Flow

1. Client sends GET request to `/api/budgets`
2. API validates the API key
3. BudgetService fetches data in the following sequence:
   - Fetch all projects with hierarchy information
   - Build project titles with proper ancestor ordering
   - Fetch budget hours in chunks for performance
   - Fetch budget costs in chunks
   - Fetch progress budgets in chunks
   - Fetch cost codes for the relevant projects
   - Combine all data with proper hierarchy
   - Format and return the combined data

### Project API Flow

1. Client sends GET request to `/api/projects`
2. API validates the API key and timezone
3. ProjectService fetches data:
   - Builds GraphQL query with pagination support
   - Fetches projects in batches with cursor-based pagination
   - Processes project hierarchy up to 7 levels deep
   - Filters children based on archived status
   - Formats project data with timezone conversion
   - Returns hierarchical project data

## Error Handling

The API provides standardized error responses:
- 400: Bad Request (invalid parameters)
- 401: Unauthorized (invalid API key)
- 500: Internal Server Error (processing errors)
- 504: Gateway Timeout (request timeout)

## Pagination and Performance

- The API uses cursor-based pagination for efficient data retrieval
- Batch processing is implemented with configurable batch sizes
- Concurrent requests are used for fetching related data
- Timeout handling is implemented for long-running requests


## Configuration

The API is configurable through environment variables:
- `BUSYBUSY_GRAPHQL_URL`: GraphQL API endpoint
- `MAX_BATCH_SIZE`: Maximum batch size for pagination
- `MAX_CONCURRENT_REQUESTS`: Maximum concurrent requests
- `DEFAULT_TIMEOUT`: Default timeout for requests 