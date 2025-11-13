"""Development server entrypoint."""
from __future__ import annotations

from .app import create_app


app = create_app("development")


if __name__ == "__main__":
    print("Starting Flask server...")
    print("Backend available at: http://localhost:5001")
    print("API base URL: http://localhost:5001/api")
    print("Demo users:")
    print("   coordinador@udem.edu.co / 123456")
    print("   profesor@udem.edu.co / 123456")
    print("   estudiante@udem.edu.co / 123456")
    print("   maria@udem.edu.co / 123456")
    print("   carlos@udem.edu.co / 123456")
    print()

    app.run(host="0.0.0.0", port=5001)
