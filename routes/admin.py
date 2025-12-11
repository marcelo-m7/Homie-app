"""
Admin routes for Homie - Feature visibility management
"""
from flask import Blueprint, render_template, request, jsonify, session
from authentication import admin_required
from database import (
    get_all_users_features, 
    set_user_feature_visibility,
    get_all_users
)
from security import csrf_protect
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/features')
@admin_required
def admin_features():
    """Admin panel for managing feature visibility"""
    try:
        users_features = get_all_users_features()
        return render_template('admin_features.html', users_features=users_features)
    except Exception as e:
        logger.error(f"Error loading admin features page: {e}")
        return jsonify({'error': 'Failed to load admin page'}), 500

@admin_bp.route('/api/users')
@admin_required
def api_get_users():
    """API endpoint to get all users and their feature settings"""
    try:
        users_features = get_all_users_features()
        return jsonify({'users': [dict(u) for u in users_features]})
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return jsonify({'error': 'Failed to get users'}), 500

@admin_bp.route('/api/feature-visibility', methods=['POST'])
@admin_required
@csrf_protect
def api_set_feature_visibility():
    """API endpoint to set feature visibility for a user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        feature_name = data.get('feature_name')
        is_visible = data.get('is_visible')
        
        if user_id is None or feature_name is None or is_visible is None:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Get the admin user ID from session
        admin_user_id = session['user']['id']
        
        # Valid features
        valid_features = ['shopping', 'chores', 'tracker', 'bills', 'budget']
        if feature_name not in valid_features:
            return jsonify({'error': 'Invalid feature name'}), 400
        
        # Set the visibility
        success = set_user_feature_visibility(
            user_id, 
            feature_name, 
            is_visible, 
            admin_user_id
        )
        
        if success:
            logger.info(f"Admin {admin_user_id} set {feature_name} visibility to {is_visible} for user {user_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update visibility'}), 500
            
    except Exception as e:
        logger.error(f"Error setting feature visibility: {e}")
        return jsonify({'error': 'Failed to update visibility'}), 500
