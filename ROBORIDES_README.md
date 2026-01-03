# RoboRides Fleet Manager

Production-ready demonstration of how autonomous vehicle fleets can integrate with The Services Exchange API to grab ridesharing jobs.

## Overview

This script shows how a roborides fleet can:
- Register vehicles as service providers
- Authenticate with the exchange
- Monitor for available ridesharing jobs
- Grab jobs using seat-based credentials
- Operate in both test and production modes

## Features

- **Clean ASCII Art Interface** - Professional command-line display
- **Test Mode** - Creates test jobs and verifies the fleet can grab them
- **Production Mode** - Grabs real jobs from the live exchange
- **Seat Authentication** - Uses golden seats from seats.dat for fleet access
- **Fleet Management** - Manages multiple vehicles simultaneously
- **Error Handling** - Robust error handling and status reporting

## Usage

### Test Mode
Creates test ridesharing jobs and attempts to grab them:

```bash
python3 roborides_fleet.py --test --vehicles 2
```

### Production Mode
Attempts to grab real ridesharing jobs from the exchange:

```bash
python3 roborides_fleet.py --production --vehicles 3
```

### Options

- `--test` - Run in test mode (creates and grabs test jobs)
- `--production` - Run in production mode (grabs real jobs)
- `--vehicles N` - Number of vehicles in fleet (default: 3, max: 3)
- `--help` - Show help message

## Prerequisites

```bash
pip install requests
```

## How It Works

### 1. Fleet Initialization
- Each vehicle is assigned a test seat from `seats.dat`
- Vehicles register as supply-side users on the exchange
- Authentication tokens are obtained for each vehicle

### 2. Test Mode Operation
- A test rider account is created
- Multiple test ridesharing jobs are submitted:
  - Denver Airport → Downtown Denver ($45)
  - Downtown Denver → Denver Tech Center ($35)
  - Denver Convention Center → Union Station ($25)
- Fleet vehicles attempt to grab the jobs

### 3. Production Mode Operation
- Fleet vehicles monitor the exchange for real ridesharing jobs
- When jobs are found, vehicles grab them based on proximity
- Seat credentials are verified for each grab attempt

### 4. Job Matching
The API uses LLM-powered matching to ensure:
- Vehicles are near the pickup location
- Capabilities match the service requirements
- Price and reputation alignment

## Seat Authentication

The script uses golden seats from `seats.dat` (first 3 seats):

```json
{
  "id": "RSX0000000",
  "phrase": "elephant lab aware runway...",
  "owner": "@satori_jojo"
}
```

Seat credentials include:
- **Seat ID**: Unique identifier
- **Owner**: Seat owner username
- **Secret**: MD5 hash of the seed phrase

## Example Output

```
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║    ██████╗  ██████╗ ██████╗  ██████╗ ██████╗ ██╗██████╗ ███████╗███████╗  ║
║    ██╔══██╗██╔═══██╗██╔══██╗██╔═══██╗██╔══██╗██║██╔══██╗██╔════╝██╔════╝  ║
║    ██████╔╝██║   ██║██████╔╝██║   ██║██████╔╝██║██║  ██║█████╗  ███████╗  ║
║    ██╔══██╗██║   ██║██╔══██╗██║   ██║██╔══██╗██║██║  ██║██╔══╝  ╚════██║  ║
║    ██║  ██║╚██████╔╝██████╔╝╚██████╔╝██║  ██║██║██████╔╝███████╗███████║  ║
║    ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝╚══════╝  ║
║                                                               ║
║           🚕  Fleet Manager for The Services Exchange  🚕     ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

🚗 Initializing fleet of 2 autonomous vehicles...
   Mode: TEST
   API: https://rse-api.com:5003

  ✓ Vehicle 1 registered as robo_1_7333
  ✓ Vehicle 1 authenticated
  ✓ Vehicle 2 registered as robo_2_7334
  ✓ Vehicle 2 authenticated

✓ Fleet initialized: 2/2 vehicles ready

📝 Creating test ridesharing jobs...

  ✓ Created: Denver Airport → Downtown Denver, CO ($45)
  ✓ Created: Downtown Denver, CO → Denver Tech Center ($35)
  ✓ Created: Denver Convention Center → Union Station Denver ($25)

✓ Created 3 test jobs

🚕 Dispatching fleet to grab jobs...

  ✓ Vehicle 1 grabbed job!
    Route: Denver Airport → Downtown Denver, CO
    Price: USD 45
    Job ID: 9e2e8820-...

============================================================
📊 FLEET DISPATCH SUMMARY
============================================================
  Total Vehicles: 2
  Jobs Grabbed:   1 ✓
  No Jobs Found:  1
  Errors:         0
============================================================

✅ SUCCESS: Fleet successfully grabbed jobs from the exchange!
```

## Integration Guide

To integrate this with your roborides fleet:

1. **Obtain Seats**: Get golden or silver seats for your fleet
2. **Update Configuration**: Replace test seats with your production seats
3. **Add Vehicle Logic**: Extend the `RoboridesVehicle` class with:
   - Real vehicle location tracking
   - Route navigation integration
   - Passenger pickup/dropoff logic
   - Payment processing
4. **Deploy**: Run continuously to monitor the exchange for jobs

## API Endpoints Used

- `POST /register` - Register vehicles as providers
- `POST /login` - Authenticate vehicles
- `POST /submit_bid` - Create ridesharing requests (test mode)
- `POST /grab_job` - Grab available jobs (with seat credentials)

## Notes

- Seat credentials must be kept secure
- Rate limiting: 1 grab_job request per 15 minutes per seat
- Jobs are matched based on location, capabilities, and reputation
- Test mode creates jobs with "TEST:" prefix for easy identification

## Production Deployment

For production use:

1. Use environment variables for seat credentials
2. Implement proper logging and monitoring
3. Add retry logic for network failures
4. Integrate with your fleet management system
5. Implement job completion and rating endpoints

## Support

For questions or issues, refer to:
- API Documentation: https://rse-api.com:5003/api_docs.html
- Repository: https://github.com/mickeyshaughnessy/theservicesexchange
