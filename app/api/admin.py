from functools import wraps

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.models.datastore_client import (
    add_user,
    get_allowed_users,
    get_pending_users,
    remove_pending_user,
    remove_user,
)
from utils.logger_config import get_logger

logger = get_logger(__name__)
admin_bp = Blueprint("admin", __name__)


def check_auth(username, password):
    """Check if a username/password combination is valid."""
    expected_username = current_app.config["ADMIN_USERNAME"]
    expected_password = current_app.config["ADMIN_PASSWORD"]

    if expected_password == "password":
        logger.warning("Using default admin password! Please set ADMIN_PASSWORD.")

    return username == expected_username and password == expected_password


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        "Could not verify your access level for that URL.\n"
        "You have to login with proper credentials",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/", methods=["GET"])
@requires_auth
def admin_dashboard():
    users = get_allowed_users()
    pending_users = get_pending_users()
    return render_template("admin.html", users=users, pending_users=pending_users)


@admin_bp.route("/approve", methods=["POST"])
@requires_auth
def admin_approve():
    user_id = request.form.get("user_id")
    user_name = request.form.get("user_name")

    if user_id and user_name:
        if add_user(user_id, user_name):
            remove_pending_user(user_id)
            flash(f"Approved: {user_name}", "success")
        else:
            flash("Failed to approve user", "error")
    else:
        flash("Missing user data", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/reject", methods=["POST"])
@requires_auth
def admin_reject():
    user_id = request.form.get("user_id")
    if user_id:
        if remove_pending_user(user_id):
            flash(f"Rejected: {user_id}", "success")
        else:
            flash("Failed to reject user", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/delete", methods=["POST"])
@requires_auth
def admin_delete():
    user_id = request.form.get("user_id")
    if user_id:
        if remove_user(user_id):
            flash(f"Deleted: {user_id}", "success")
        else:
            flash("Failed to delete user", "error")

    return redirect(url_for("admin.admin_dashboard"))
