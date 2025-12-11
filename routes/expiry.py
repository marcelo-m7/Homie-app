"""
Expiry tracker routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash
from authentication import login_required, api_auth_required, feature_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

expiry_bp = Blueprint('expiry', __name__)

@expiry_bp.route('/expiry')
@login_required
@feature_required('tracker')
def expiry_list():
    """Display the expiry tracker page"""
    conn = get_db_connection()
    
    # Get all expiry items with user information
    items = conn.execute('''
        SELECT e.*, u.username as added_by_username,
               CASE 
                   WHEN e.expiry_date < date('now') THEN 'expired'
                   WHEN e.expiry_date <= date('now', '+7 days') THEN 'warning'
                   WHEN e.expiry_date <= date('now', '+30 days') THEN 'upcoming'
                   ELSE 'future'
               END as status,
               CAST(julianday(e.expiry_date) - julianday('now') AS INTEGER) as days_remaining
        FROM expiry_items e
        LEFT JOIN users u ON e.added_by = u.id
        ORDER BY e.expiry_date ASC
    ''').fetchall()
    
    conn.close()
    return render_template('expiry_tracker.html', items=items)

@expiry_bp.route('/expiry/add', methods=['POST'])
@login_required
@feature_required('tracker')
def add_expiry():
    """Add a new expiry item via form submission"""
    try:
        item_name = sanitize_input(request.form.get('item_name', '').strip())
        expiry_date = request.form.get('expiry_date', '').strip()
        
        if not item_name or not expiry_date:
            flash('Item name and expiry date are required', 'error')
            return redirect(url_for('expiry.expiry_list'))
        
        # Validate date format
        try:
            from datetime import datetime
            datetime.strptime(expiry_date, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'error')
            return redirect(url_for('expiry.expiry_list'))
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO expiry_items (item_name, expiry_date, added_by)
            VALUES (?, ?, ?)
        ''', (item_name, expiry_date, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added expiry item: {item_name} expires on {expiry_date}")
        flash('Expiry item added successfully', 'success')
        return redirect(url_for('expiry.expiry_list'))
        
    except Exception as e:
        logger.error(f"Error adding expiry item: {e}")
        flash('Failed to add expiry item', 'error')
        return redirect(url_for('expiry.expiry_list'))

@expiry_bp.route('/api/expiry/add', methods=['POST'])
@api_auth_required
@csrf_protect
@feature_required('tracker')
def add_expiry_item_api():
    """Add a new expiry item via API"""
    try:
        data = request.get_json()
        if not data or 'item_name' not in data or 'expiry_date' not in data:
            return jsonify({'error': 'Item name and expiry date are required'}), 400
        
        item_name = sanitize_input(data['item_name'].strip())
        if not item_name:
            return jsonify({'error': 'Item name cannot be empty'}), 400
        
        # Validate and parse expiry date
        try:
            expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid expiry date format (use YYYY-MM-DD)'}), 400
        
        # Check if date is not too far in the past
        today = date.today()
        if expiry_date < today - timedelta(days=7):
            return jsonify({'error': 'Expiry date cannot be more than a week in the past'}), 400
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO expiry_items (item_name, expiry_date, added_by)
            VALUES (?, ?, ?)
        ''', (item_name, expiry_date.isoformat(), user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added expiry item: {item_name} - {expiry_date}")
        return jsonify({'success': True, 'message': 'Expiry item added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding expiry item: {e}")
        return jsonify({'error': 'Failed to add expiry item'}), 500

@expiry_bp.route('/expiry/delete', methods=['POST'])
@login_required
@feature_required('tracker')
def delete_expiry():
    """Delete an expiry item via form submission"""
    try:
        item_id = request.form.get('item_id')
        if not item_id:
            flash('Item ID is required', 'error')
            return redirect(url_for('expiry.expiry_list'))
        
        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            flash('Invalid item ID', 'error')
            return redirect(url_for('expiry.expiry_list'))
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        
        # Check if item exists and user has permission
        item = conn.execute('SELECT * FROM expiry_items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            flash('Item not found', 'error')
            return redirect(url_for('expiry.expiry_list'))
        
        # Delete the item
        conn.execute('DELETE FROM expiry_items WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} deleted expiry item {item_id}")
        flash('Expiry item deleted successfully', 'success')
        return redirect(url_for('expiry.expiry_list'))
        
    except Exception as e:
        logger.error(f"Error deleting expiry item: {e}")
        flash('Failed to delete expiry item', 'error')
        return redirect(url_for('expiry.expiry_list'))

@expiry_bp.route('/api/expiry/delete/<int:item_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
@feature_required('tracker')
def delete_expiry_item_api(item_id):
    """Delete an expiry item via API"""
    try:
        conn = get_db_connection()
        
        # Validate ownership or admin rights
        if not validate_ownership(conn, 'expiry_items', item_id, session['user']):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete the item
        result = conn.execute('DELETE FROM expiry_items WHERE id = ?', (item_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Expiry item not found'}), 404
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} deleted expiry item {item_id}")
        
        return jsonify({'success': True, 'message': 'Expiry item deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting expiry item {item_id}: {e}")
        return jsonify({'error': 'Failed to delete expiry item'}), 500