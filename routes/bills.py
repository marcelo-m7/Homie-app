"""
Bills routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session
from authentication import login_required, api_auth_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

bills_bp = Blueprint('bills', __name__)

@bills_bp.route('/bills')
@login_required
def bills_list():
    """Display the bills page"""
    conn = get_db_connection()
    
    # Get all bills with user information
    bills = conn.execute('''
        SELECT b.*, u.username as added_by_name
        FROM bills b
        LEFT JOIN users u ON b.added_by = u.id
        ORDER BY b.due_day ASC, b.created_at DESC
    ''').fetchall()
    
    conn.close()
    return render_template('bills.html', bills=bills)

@bills_bp.route('/api/bills/add', methods=['POST'])
@api_auth_required
@csrf_protect
def add_bill():
    """Add a new bill via API"""
    try:
        data = request.get_json()
        if not data or 'bill_name' not in data or 'amount' not in data or 'due_day' not in data:
            return jsonify({'error': 'Bill name, amount, and due day are required'}), 400
        
        bill_name = sanitize_input(data['bill_name'].strip())
        if not bill_name:
            return jsonify({'error': 'Bill name cannot be empty'}), 400
        
        try:
            amount = float(data['amount'])
            if amount < 0:
                return jsonify({'error': 'Amount cannot be negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400
        
        try:
            due_day = int(data['due_day'])
            if due_day < 1 or due_day > 31:
                return jsonify({'error': 'Due day must be between 1 and 31'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid due day format'}), 400
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO bills (bill_name, amount, due_day, added_by)
            VALUES (?, ?, ?, ?)
        ''', (bill_name, amount, due_day, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added bill: {bill_name} - ${amount}")
        return jsonify({'success': True, 'message': 'Bill added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding bill: {e}")
        return jsonify({'error': 'Failed to add bill'}), 500

@bills_bp.route('/api/bills/delete/<int:bill_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
def delete_bill(bill_id):
    """Delete a bill"""
    try:
        conn = get_db_connection()
        
        # Validate ownership or admin rights
        if not validate_ownership(conn, 'bills', bill_id, session['user']):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete the bill
        result = conn.execute('DELETE FROM bills WHERE id = ?', (bill_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Bill not found'}), 404
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} deleted bill {bill_id}")
        
        return jsonify({'success': True, 'message': 'Bill deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting bill {bill_id}: {e}")
        return jsonify({'error': 'Failed to delete bill'}), 500